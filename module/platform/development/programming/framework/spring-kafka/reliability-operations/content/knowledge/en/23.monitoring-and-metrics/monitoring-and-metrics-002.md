# micrometerEnabled

In a production Spring Kafka system, seeing "the consumer is still RUNNING" is not enough to confirm the service is healthy. A listener may be processing slowly, throwing exceptions repeatedly, retrying multiple times, or failing to perform the required business side effects. To observe these issues, Spring Kafka integrates with **Micrometer** and can automatically record execution times of Kafka listeners.

The **micrometerEnabled** property on **ContainerProperties** controls whether **Micrometer Timer metrics for listener invocations** are enabled or disabled. When this mechanism is enabled and Micrometer is on the classpath, Spring Kafka can create timers named **spring.kafka.listener**, attaching tags to distinguish listeners and execution outcomes. These metrics let you answer questions such as whether the listener is still being invoked, what the success/failure invocation ratio is, which listener has rising latency, and whether a new deployment increased record processing duration.

However, **micrometerEnabled is not a switch that enables all Kafka observability**. It does not export metrics to Prometheus by itself, does not automatically measure consumer lag or broker health, does not guarantee distributed tracing, and does not replace business metrics. Modern Spring Kafka also provides **Micrometer Observation** via the `observationEnabled` property, which has a different scope and configuration. Understanding this boundary is the core of this lesson in the **Monitoring and metrics** chapter of **Spring Kafka Reliability Operations**.

## 1. Three observability layers to distinguish

A Kafka application typically needs to monitor at least three layers:

1. **Listener invocation metrics:** time the framework spends invoking the listener, success/failure outcomes, exception class; this is the scope directly related to `micrometerEnabled`.
2. **Kafka client metrics:** `KafkaConsumer`/`KafkaProducer` details such as fetch rate, records consumed, request latency, coordinator/rebalance, or send retries; these come from Kafka clients and their corresponding collectors.
3. **Business reliability metrics:** number of successfully processed orders, duplicate rate, retries exhausted, records in DLT, successful database side effects, consumer lag relative to SLA; many of these metrics require custom application instrumentation.

~~~mermaid
flowchart TB
    K["Kafka broker / partitions"] --> C["KafkaConsumer"]
    C --> L["Spring Kafka Listener Container"]
    L --> B["@KafkaListener / business processing"]
    B --> D["Database / HTTP / downstream"]
    L --> T["Micrometer listener timers"]
    C --> M["Kafka client metrics"]
    B --> X["Business metrics"]
    T --> R["MeterRegistry"]
    M --> R
    X --> R
    R --> P["Actuator / Prometheus / monitoring backend"]
~~~

A steadily increasing listener metric does not prove downstream side effects committed exactly once. Conversely, the Kafka client may still poll normally while the listener is failing continuously. Therefore, you should not replace all Kafka dashboards with a single timer named `spring.kafka.listener`.

### 1.1 Meaning table for each layer

| Required observation | Primary source | Directly provided by micrometerEnabled? |
|---|---|---|
| Number of listener method invocations | Listener Timer count | Yes, when the timer is recorded |
| Listener invocation processing time | Listener Timer | Yes |
| Listener invocation threw exception | Listener Timer result/exception tags | Yes, within invocation scope |
| Kafka consumer records-lag-max | Kafka client metrics | No |
| Consumer group committed offset / lag per partition | Kafka broker/admin/monitoring | No |
| Kafka producer request latency | Producer/client metrics | No |
| Record routed to Dead Letter Topic | Recovery instrumentation/producer metrics | Not automatically |
| Business order written to DB successfully | Business metrics or DB | Not automatically |
| Distributed trace between producer and consumer | Micrometer Observation/Tracing and propagation | Not by micrometerEnabled alone |
| Service health endpoint | Spring Boot Actuator Health and checks | No |

## 2. Where does micrometerEnabled live?

In Spring Kafka, the relevant property is:

~~~java
factory.getContainerProperties().setMicrometerEnabled(true);
~~~

This is a setter on **ContainerProperties**, used when configuring a listener container or listener container factory. For Kafka listener containers, this property controls creating Micrometer timers in the listener processing flow when framework conditions are satisfied.

Example:

~~~java
@Configuration
public class OrdersKafkaConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        factory.setBatchListener(false);

        factory.getContainerProperties()
               .setMicrometerEnabled(true);

        return factory;
    }
}
~~~

Listener:

~~~java
@Component
public class OrdersListener {

    private final OrderService orderService;

    public OrdersListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
        id = "orders-projection",
        topics = "orders",
        groupId = "orders-projection-prod",
        containerFactory = "ordersKafkaListenerContainerFactory"
    )
    public void handle(OrderEvent event) {
        orderService.apply(event);
    }
}
~~~

The `OrderEvent`/`OrderService` classes in the example are hypothetical models and services. In a real project, `ConsumerFactory` must also include deserializers, security, bootstrap servers, and appropriate consumer properties.

### 2.1 Default and presence of Micrometer

In Spring Kafka lines that support Micrometer listener timers, **micrometerEnabled generally defaults to true**. However, a timer can only be created when the appropriate Micrometer library is on the classpath and a registry is configured to record at runtime.

Therefore, there are three distinct situations:

| State | Expected outcome |
|---|---|
| micrometerEnabled=true, Micrometer ready | Spring Kafka can create listener timers |
| micrometerEnabled=false | Automatic Listener Timers from this mechanism are disabled |
| micrometerEnabled=true but missing dependency/registry/export | Metric may not appear in backend despite property being true |

Do not assume that setting `true` is enough for metrics to appear in Grafana. Verify the full data path **listener → meter registry → exporter → Prometheus/monitoring backend**.

### 2.2 Explicit enabling vs. relying on defaults

Even though the current default is `true`, explicit configuration is helpful when:

- A project wants to state clearly that a listener must be timed.
- Multiple listener factories exist with different observability policies.
- Integration tests assert on metrics.
- Migrating between Micrometer Timer and Micrometer Observation.
- Selectively disabling metrics in a high-cardinality or high-cost workload.

Do not scatter enable/disable calls across multiple factory customizers without knowing their precedence, because the effective setting on the container may differ from what someone reading YAML expects.

## 3. What duration does a listener Timer measure?

For a synchronous record listener, the timer wraps the listener invocation execution instrumented by Spring Kafka.

Example:

~~~java
@KafkaListener(
    id = "orders-projection",
    topics = "orders",
    groupId = "orders-projection-prod"
)
public void handle(OrderCreated order) {
    validate(order);
    orderService.apply(order);
}
~~~

An invocation can include `validate()` and `orderService.apply()`. When the listener returns normally, the framework can record a timer for a successful invocation. When an exception escapes the listener per framework semantics, an error timer can be recorded with the corresponding result/exception tags.

However, distinguish the following milestones:

~~~text
KafkaConsumer.poll()
  -> ConsumerRecord deserialize
  -> Spring listener invocation START
       -> validate
       -> DB / HTTP processing
  -> Listener invocation END
  -> Container error handling / acknowledgment / offset commit
  -> Other consumer lifecycle operations
~~~

**The Listener Timer does not by default measure the entire end-to-end path from when the producer sends a record to when the offset is committed**, nor does it necessarily include time waiting for `BackOff` or a DLT publisher to finish. Its primary scope is the listener invocation.

### 3.1 Record processing latency vs. event freshness

Suppose an event is sent by a producer at 10:00:00, sits in Kafka for two minutes due to consumer lag, and then the listener processes it successfully in 50 ms.

- The Listener Timer records roughly 50 ms.
- End-to-end event latency from producer to completion is roughly two minutes.
- Consumer lag caused most of the delay.
- Looking only at `spring.kafka.listener` will miss the freshness issue entirely.

To measure event age, use a reliable source timestamp and supplemental instrumentation; account for clock skew, Kafka timestamp semantics, and cross-system delays.

### 3.2 Listeners with async operations

Example:

~~~java
@KafkaListener(topics = "orders")
public void handle(OrderEvent event) {
    executor.submit(() -> process(event));
}
~~~

The method can return almost immediately while the actual task has not yet finished. The invocation timer then **does not capture the full time to complete business work on the executor**. Worse, the offset might be committed before side effects occur if acknowledgment design is unsuitable.

When using async listener processing:

- Separately measure the time until the business task finishes.
- Use bounded queues and backpressure.
- Synchronize offset acknowledgment with completion per appropriate Kafka/Spring design.
- Do not treat a submit method's timer success as business success.
- Ensure async task exceptions are observed and recovered.

## 4. Meter name and common tags

In Spring Kafka's listener timers mechanism, the common meter is named:

~~~text
spring.kafka.listener
~~~

The Micrometer Timer stores information such as **count**, **totalTime**, and **max** through the `MeterRegistry` API. Tags in common Spring Kafka versions include:

- **name:** listener/container name per framework.
- **result:** success or failure, typically distinguishing `success`/`failure`.
- **exception:** exception type or a value indicating no exception.
- **Static or dynamic tags:** added via `ContainerProperties` when supported.

Logical illustration of several time series:

~~~text
spring.kafka.listener
  name=orders-projection-0
  result=success
  exception=none

spring.kafka.listener
  name=orders-projection-0
  result=failure
  exception=DataAccessResourceFailureException
~~~

This illustrates how metrics are grouped, not a guarantee that every framework version emits identical tags. With concurrent listeners, the meter tag name may reflect child containers and use a suffix.

### 4.1 What does Success mean?

A timer's success usually means **the listener invocation completed in a way the framework considers error-free**. It does not prove:

- The DB transaction committed durably.
- The Kafka consumer offset committed.
- An external Kafka transaction committed.
- Downstream received the HTTP request exactly once.
- The record will not be re-read after restart.
- The entire business workflow completed.

If a listener catches an exception, logs it, and returns normally, the timer may record success:

~~~java
@KafkaListener(topics = "orders")
public void handle(OrderEvent event) {
    try {
        orderService.apply(event);
    }
    catch (Exception ex) {
        log.error("Failed but swallowed", ex);
        // Method returns normally.
    }
}
~~~

This is an anti-pattern if the exception requires a retry or rollback. A success metric cannot fix a listener that hides business errors.

### 4.2 What does Failure mean?

Failure indicates the listener invocation was recorded as an error by the framework. It does not yet distinguish:

- A transient DB timeout that can be retried.
- A poison message requiring the DLT.
- A business validation error.
- A serialization/conversion error.
- A transaction rollback occurring after the callback.

For a record that fails three times before succeeding, the listener timer may record several failed invocations and one success invocation. This is **listener invocation count**, not necessarily the count of unique Kafka records.

## 5. Counting invocations vs. counting unique records

A record at `orders-0` offset 100 may be retried multiple times by `DefaultErrorHandler`.

~~~text
record orders-0@100
  attempt 1 -> listener throws
  attempt 2 -> listener throws
  attempt 3 -> listener returns success
~~~

Metrics may record three listener invocations:

~~~text
failure count += 2
success count += 1
~~~

Yet the number of unique Kafka records processed successfully is one, counting only the record at offset 100.

Do not use total listener timer count as the count of unique completed business events in systems with retries, rebalances, or at-least-once redelivery.

### 5.1 DLT and recovery do not appear completely in the timer

If `DefaultErrorHandler` recovers a record by publishing it to a DLT, the listener may have thrown an exception while recovery succeeded at the container layer. A failed invocation timer is not a "DLT publish succeeded" metric.

Other metrics are needed:

- Retry attempt count.
- Retry exhausted count.
- DLT publish success/failure.
- Age of oldest DLT event.
- Consumer offset progression.
- Business operation completion.

### 5.2 Deserialization can fail before the listener

If a deserializer throws an exception during `KafkaConsumer.poll()`, `@KafkaListener` is not called yet. Consequently, the listener invocation timer may **not increment** for that record, even though the consumer is encountering critical errors.

With `ErrorHandlingDeserializer` and `DefaultErrorHandler`, errors may be routed into the recovery flow before the listener is called. Therefore, dedicated metrics for deserialization errors and DLT are necessary.

**Do not use listener timer failure rate as the sole indicator for all consumer errors.**

## 6. Enabling and disabling on the right listener factory

An application often has multiple `KafkaListenerContainerFactory` beans:

~~~text
ordersRecordFactory  -> orders consumer
paymentsBatchFactory -> payments consumer
auditFactory         -> audit consumer
~~~

If `micrometerEnabled` is only enabled on `ordersRecordFactory`, you cannot conclude metrics for payments/audit follow the same policy.

Example of explicitly disabling on another workload:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, AuditEvent>
auditKafkaListenerContainerFactory(
        ConsumerFactory<String, AuditEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, AuditEvent>();

    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties()
           .setMicrometerEnabled(false);

    return factory;
}
~~~

Some valid reasons to disable timers:

- The workload has its own instrumentation approach.
- Micrometer Observation is enabled and you want to avoid confusing overlapping metrics.
- Metric collection overhead must be reduced in a specialized component.
- There is a cardinality issue and the metric tagging policy must be redesigned.

However, disabling `micrometerEnabled` can also starve dashboards that rely on `spring.kafka.listener`. Before changing it, know which metrics the monitoring backend reads and have a migration plan.

### 6.1 Configurers and auto-configuration

Spring Boot can auto-configure a listener container factory and support customization via extension points. If the application creates a custom factory itself, verify that it preserves required Boot configurations, such as:

- Appropriate `ConsumerFactory`.
- Error handler.
- Concurrency/AckMode.
- Interceptors.
- Container observation settings.
- Message converter.
- Transaction manager.

Do not create a custom factory just to set `micrometerEnabled` and accidentally drop retry/transaction settings from the previous factory.

## 7. Attaching static tags with micrometerTags

In supported Spring Kafka versions, `ContainerProperties` can configure **micrometerTags** to add static tags to listener timers.

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties()
           .setMicrometerEnabled(true);

    factory.getContainerProperties().setMicrometerTags(
        Map.of(
            "domain", "orders",
            "pipeline", "projection",
            "stage", "consumer"
        )
    );

    return factory;
}
~~~

Tags help group metrics in dashboards:

- Domain: orders/payments/inventory.
- Pipeline: projection/notification/indexing.
- Stage: consumer or workload category.
- Environment: prod/staging if environment is not attached automatically by the exporter.

### 7.1 Tags must have a bounded set of values

A metric with 5 listener names, 2 results, 10 exceptions, and 3 domains can produce up to about 300 series before counting instance/pod labels. Adding `eventId` or `orderId` as a tag can multiply series with every record.

**Do not attach the following values as Micrometer tags for listener timers:**

- orderId.
- eventId.
- requestId.
- Kafka offset.
- High-cardinality raw message keys.
- User ID.
- Full exception message.
- Payloads or PII.

These values belong in structured logs/traces with restricted access, not in metric tags.

### 7.2 Container tags vs. monitoring system labels

Some labels are added by Prometheus scraping or Kubernetes, such as instance, pod, namespace, or job. They multiply cardinality.

When designing dashboards, compute total cardinality after the exporter adds its labels, not just the `Map` passed to `setMicrometerTags()`.

### 7.3 Do not hardcode dynamic instance IDs in tags unnecessarily

A listener ID containing a UUID or timestamp that changes per deploy creates new series on every rollout. While helpful for debugging, it can force the backend to retain thousands of unnecessary time series.

Instead, use:

- Stable logical listener IDs.
- Infrastructure-managed pod/instance labels when truly needed.
- A controlled set of domain/pipeline tags.
- Trace ID/event ID in logs/traces, never as Prometheus metric labels.

## 8. Dynamic micrometerTagsProvider

Some Spring Kafka versions include **micrometerTagsProvider**, allowing tags to be added based on `ConsumerRecord`. This is an advanced mechanism and its API must be checked for your actual version.

Illustrative example:

~~~java
factory.getContainerProperties()
       .setMicrometerTagsProvider(record ->
           Map.of(
               "topic", record.topic()
           )
       );
~~~

Good point of the example: `topic` is a bounded set, generally suitable as a tag if the topic count is not too large.

Dangerous point: switching to `record.key()` or `eventId`, which can have millions of values. The metrics backend can overload, waste memory, and inflate storage costs.

### 8.1 Dynamic tags and timer lifetime

To record a timer, the framework must resolve a meter identity from its name and tags. If every record yields a unique tag set, every invocation can register a different meter. That is not an effective way to use Micrometer.

Establish rules:

1. Only use tags with a bounded set of values.
2. Never leak personal data into tags.
3. Never use exception messages as tags.
4. Budget cardinality in the design.
5. Monitor active meter series counts before and after rollout.
6. Verify behavior for your Spring Kafka and Micrometer versions.

### 8.2 When is a provider unnecessary?

If each listener always subscribes to exactly one topic, the topic tag can be inferred from the listener name or static configuration. Using a dynamic provider just to repeat static information adds complexity without increasing analytical value.

For a listener subscribed to multiple topics, a topic tag may be useful, provided cardinality is controlled.

## 9. Spring Boot Actuator and MeterRegistry

**micrometerEnabled=true does not create a Prometheus endpoint on its own.** A suitable Micrometer registry and exporter are required.

A Spring Boot application can use these dependencies:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("io.micrometer:micrometer-registry-prometheus")
    implementation("org.springframework.kafka:spring-kafka")
}
~~~

Dependency versions should be managed by the Spring Boot BOM/platform; avoid pinning Micrometer versions incompatible with your Spring Boot/Spring Kafka versions.

Example Actuator configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    prometheus:
      access: unrestricted
~~~

The `access` property and security behavior vary across Spring Boot versions. The config above conveys the idea of exposing the endpoint; check your dependency version and **protect the endpoint** with appropriate network policies, authentication, or scrape access controls.

Some Boot versions use different enablement or access policy mechanisms; do not copy this block verbatim while ignoring production security.

### 9.1 Metrics data path

~~~mermaid
flowchart LR
    L["Spring Kafka listener timer"] --> MR["MeterRegistry"]
    MR --> A["Spring Boot Actuator"]
    A --> EP["/actuator/prometheus"]
    EP --> PR["Prometheus scrape"]
    PR --> G["Grafana dashboards"]
~~~

For data to appear, you need:

- The listener actually runs and produces observations/timer records.
- A suitable `MeterRegistry` and registry exporter exist.
- The Prometheus endpoint is properly exposed.
- The monitoring collector can reach the endpoint.
- The scrape config selects the right target.
- No `MeterFilter` blocks the metric or unexpectedly renames names/tags.

### 9.2 Checking via Actuator metrics

Spring Boot Actuator's metrics endpoint accepts the logical Micrometer meter name:

~~~text
GET /actuator/metrics/spring.kafka.listener
~~~

In systems where the metric exists, the response typically shows measurements and `availableTags`. Do not expect a timer to appear before a corresponding listener invocation has occurred, depending on how meters are registered and runtime lifecycle.

For Prometheus output:

~~~text
GET /actuator/prometheus
~~~

The metric name in Prometheus differs from the logical Micrometer name due to naming conventions and time units.

## 10. Metric names in Prometheus

A Micrometer Timer is typically exported to Prometheus as series with suffixes:

~~~text
spring_kafka_listener_seconds_count
spring_kafka_listener_seconds_sum
spring_kafka_listener_seconds_max
~~~

Actual names and series also depend on the registry version, histogram/percentile settings, and export configuration. To avoid mistakes, inspect `/actuator/prometheus` in your live runtime.

Illustrative PromQL example:

~~~promql
sum by (name) (
  rate(spring_kafka_listener_seconds_count{result="success"}[5m])
)
~~~

This is the rate of **successful listener invocations**, not the number of unique orders.

Failed invocation ratio:

~~~promql
sum(rate(spring_kafka_listener_seconds_count{result="failure"}[5m]))
/
clamp_min(
  sum(rate(spring_kafka_listener_seconds_count[5m])),
  0.001
)
~~~

At low traffic, error ratios fluctuate sharply. Combine with a minimum attempt/request threshold before alerting on percentages rather than setting an error percentage threshold that ignores traffic volume.

### 10.1 Average listener duration

If the exporter provides `_sum` and `_count`:

~~~promql
sum(rate(spring_kafka_listener_seconds_sum[5m]))
/
clamp_min(
  sum(rate(spring_kafka_listener_seconds_count[5m])),
  0.001
)
~~~

The result is **average invocation duration in seconds**, across the selected series. Average values are useful but easily hide tail latency.

### 10.2 p95/p99 latency requires histograms or suitable distributions

You cannot compute a reliable p95 from `_sum` and `_count` alone. With Prometheus histograms enabled, you can use:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, name) (
    rate(spring_kafka_listener_seconds_bucket[5m])
  )
)
~~~

The `_bucket` series **does not appear automatically in every configuration**. Histogram/distribution publication must be enabled per your Micrometer/Spring Boot version, balancing bucket counts and cardinality cost.

A common configuration in Spring Boot Micrometer:

~~~properties
management.metrics.distribution.percentiles-histogram.spring.kafka.listener=true
~~~

This property is an example of enabling histograms in supported versions; confirm effective configuration and registry naming conventions. Enable histograms selectively only on timers that truly need percentile SLOs; many buckets multiplied by many tags can inflate metric series significantly.

### 10.3 Querying by specific listener

When runtime `name` tags reflect child IDs, you can use regex matching per convention:

~~~promql
sum(
  rate(
    spring_kafka_listener_seconds_count{
      name=~"orders-projection.*",
      result="failure"
    }[5m]
  )
)
~~~

Overly broad regexes can match `orders-projection-canary` or a similarly named retry listener. In production dashboards, standardize naming conventions and labels to avoid accidental grouping.

## 11. Micrometer Timer vs. Kafka consumer metrics

The Micrometer listener timer does not show fetch rate, partition assignments, or consumer lag.

The Kafka client has its own set of metrics from `KafkaConsumer`/`KafkaProducer`. Spring Kafka also supports Micrometer integration for clients through factory listeners or Kafka client metrics binders, depending on framework version and configuration.

Supported Spring Kafka versions include components such as:

- **MicrometerConsumerListener**: integrates Micrometer with `ConsumerFactory` to collect Kafka consumer metrics.
- **MicrometerProducerListener**: integrates with `ProducerFactory` to collect Kafka producer metrics.
- Other binders/auto-configuration provided by Spring Boot/Micrometer.

These are **different** from `setMicrometerEnabled(true)` on `ContainerProperties`.

### 11.1 Conceptual wiring example

~~~java
@Bean
ConsumerFactory<String, OrderEvent> ordersConsumerFactory(
        MeterRegistry registry,
        Map<String, Object> consumerProperties) {

    var factory =
        new DefaultKafkaConsumerFactory<String, OrderEvent>(
            consumerProperties
        );

    factory.addListener(
        new MicrometerConsumerListener<>(registry)
    );

    return factory;
}
~~~

This code snippet illustrates the concept and requires appropriate imports and consumer serializer configs. In a Spring Boot application, some client metrics may already be auto-configured; **do not add the listener twice** if the project already has equivalent instrumentation.

### 11.2 Separating monitoring questions

| Question | Appropriate mechanism |
|---|---|
| How long does the listener take to process a record? | Listener Timer or Observation |
| Is the consumer still polling? | Consumer metrics, poll monitoring, events |
| What is the group's lag per partition? | Kafka group lag monitoring |
| Does the producer have retries or request timeouts? | Producer/client metrics |
| How long did an event wait since publish? | Event timestamp + application instrumentation |
| How many times did the listener fail? | Listener failure timer and error handler metrics |
| Did the DLT publish succeed? | DLT publisher/recoverer monitoring |
| Has the database committed business state? | Business/DB metrics and audit |

If you only enable `micrometerEnabled` and then ask "why is consumer lag rising?", add the right metrics instead of looking for an unrelated property on the timer.

## 12. micrometerEnabled and observationEnabled

Modern Spring Kafka provides **Micrometer Observation** to support metrics and tracing based on the Micrometer Observation API.

A container can be configured with:

~~~java
factory.getContainerProperties().setObservationEnabled(true);
~~~

**observationEnabled** is not equivalent to **micrometerEnabled**:

- `micrometerEnabled` controls the **legacy Micrometer listener timers mechanism**.
- `observationEnabled` controls **Observation instrumentation** on the listener; it can connect metrics and tracing depending on `ObservationRegistry`/handlers.
- When observation is enabled, the legacy timer mechanism may be **disabled or not recorded in parallel** per Spring Kafka version semantics, letting Observation handle that instrumentation.

### 12.1 Two false expectations to avoid

**First misconception:** "Enabling `observationEnabled` guarantees `spring.kafka.listener` dashboards keep all tags and series unchanged."

Observation may create different metrics or different tags per conventions. Meter names or schemas can change depending on Spring Kafka/Micrometer versions and custom observation conventions. During migration, inspect actual metrics and update dashboards/alerts intentionally.

**Second misconception:** "If `micrometerEnabled=false`, no Kafka metrics can exist at all."

Kafka client metrics, custom meters, and observation-based metrics can still exist if enabled separately. Disabling one timer does not turn off the entire Micrometer infrastructure.

### 12.2 Policy selection example

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);

    // Option 1: legacy listener timers.
    factory.getContainerProperties().setMicrometerEnabled(true);
    factory.getContainerProperties().setObservationEnabled(false);

    return factory;
}
~~~

Or with tracing/observation:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersObservedListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);

    // Option 2: Micrometer Observation.
    factory.getContainerProperties().setObservationEnabled(true);

    return factory;
}
~~~

In option two, do not assume `setMicrometerEnabled(true)` forces legacy timers to run alongside Observation; the framework may use a separate instrumentation path. Observe effective metric output at runtime.

### 12.3 When to use Timer vs. Observation?

| Need | Legacy Listener Timer | Observation |
|---|---|---|
| Count invocations and measure duration | Suitable | Suitable when metrics handler is configured |
| Keep existing Timer dashboards | Minimal changes | Requires migration verification |
| Distributed tracing across Kafka | Insufficient alone | Better suited with tracing/propagation |
| Correlation with trace/span | Needs extra instrumentation | Supported by Observation/Tracing system |
| Only need a few simple metrics | Fewer moving parts | May be unnecessary overhead |
| Propagate context producer-to-consumer | Not from micrometerEnabled | Requires proper Observation/Tracing config |

Do not choose Observation merely because the name sounds "newer." Choose based on observability goals, versions, registry, tracing backend, and operational readiness.

## 13. Metrics architecture for record vs. batch listeners

Spring Kafka supports both record listeners and batch listeners.

### 13.1 Record listener

~~~java
@KafkaListener(
    id = "orders-record",
    topics = "orders",
    containerFactory = "recordFactory"
)
public void onRecord(OrderEvent event) {
    service.process(event);
}
~~~

For a record listener, one invocation typically corresponds to one record, so the timer count is close to the number of deliveries into the listener. However, a record may be invoked again due to retries/rebalances, so count is not the number of unique records.

### 13.2 Batch listener

~~~java
@KafkaListener(
    id = "orders-batch",
    topics = "orders",
    containerFactory = "batchFactory"
)
public void onBatch(List<OrderEvent> events) {
    service.processBatch(events);
}
~~~

For a batch listener, a single invocation can process multiple records. Timer count = number of **batch invocations**, not the number of records in the batch.

Example:

~~~text
Batch 1: 120 records -> 1 listener invocation
Batch 2: 100 records -> 1 listener invocation
Batch 3: 80 records  -> 1 listener invocation

Listener Timer count: about 3
Business records attempted: 300
~~~

If you evaluate throughput in records/second from a batch listener's Timer count without measuring batch size, dashboards can vastly underreport reality.

### 13.3 Measuring actual batch throughput

You can create a custom `Counter` or `DistributionSummary`:

~~~java
@Component
public class OrderBatchMetrics {

    private final Counter batchRecordsAttempted;

    public OrderBatchMetrics(MeterRegistry registry) {
        this.batchRecordsAttempted = Counter.builder(
                "orders.batch.records.attempted"
            )
            .description("Records attempted by the batch listener")
            .register(registry);
    }

    public void recordBatchSize(int size) {
        batchRecordsAttempted.increment(size);
    }
}
~~~

This is the count of records **attempted**, not unique committed business records. If a batch fails and retries, the counter can double-count. Define metric semantics clearly.

## 14. Error handlers and retries skew the success/failure ratio

A record that fails transiently twice before succeeding can produce:

~~~text
Listener attempt 1 -> failure
Listener attempt 2 -> failure
Listener attempt 3 -> success
~~~

If a dashboard calculates:

~~~text
success rate = success listener invocations / total invocations
~~~

then this record has a 1/3 success ratio, even though the business operation eventually succeeded. This metric reflects **listener attempt success rate**, not **final recovery success rate**.

Complementary metrics are needed:

| Metric | Unit to define |
|---|---|
| listener_attempts_total | Number of listener invocations |
| listener_failures_total | Number of failed invocations |
| record_retries_total | Number of retry attempts by error handler |
| recovery_success_total | Number of records successfully recovered |
| dlt_published_total | Number of records actually written to DLT successfully |
| business_completed_total | Number of completed business operations |
| business_duplicate_total | Number of previously processed event IDs |

Several of the metrics above are custom metrics, not automatically exported by Spring Kafka.

### 14.1 Do not equate recovery with success

If `DeadLetterPublishingRecoverer` successfully publishes a failing record to the DLT, the handler may let the consumer move on. This is **successful recovery/quarantine**, not that the listener completed the business operation.

A dashboard that only sees Kafka lag dropping and one failure in the listener timer will not show that an event was quarantined. Monitor DLT and business state separately.

### 14.2 Transaction rollback after the listener

In a transactional listener, the method may return, yet the subsequent Kafka transaction commit or offset coordination may fail. Listener Timer success is not proof that the Kafka transaction commit completed.

If the goal is Kafka exactly-once processing, monitor transaction begin/commit/abort, producer fencing, consumer offsets, and downstream `read_committed`, in addition to listener timing.

## 15. Metrics and consumer lag

Consumer lag is a crucial signal, yet `micrometerEnabled` does not compute it.

Lag typically requires comparing:

- The partition's log end offset.
- The consumer group's committed offset.
- Assignment/ownership and measurement timing.

Kafka client metrics may include `records-lag-max` or other lag measurements, but they do not fully replace group/topic/partition lag monitoring from Kafka Admin/monitoring services.

### 15.1 Why is the timer low while lag keeps rising?

Possible reasons:

- Producer writes 10,000 records/second while consumer processes 7,000.
- The consumer is paused.
- Poll/rebalance is slow.
- A poison record causes blocking retries.
- The consumer is assigned only a few hot partitions.
- The listener runs async and logs short timer durations while a downstream queue grows.
- The broker/network is slow on fetch.

The Micrometer listener timer mainly helps find **processing duration**. Explaining lag requires rate, partition assignment, pause status, and client metrics.

### 15.2 SLOs should be based on business goals

Example SLO:

~~~text
99% of OrderCreated events must complete projection
within 2 minutes of the Kafka append timestamp.
~~~

A listener p99 under 100 ms is good, but insufficient to prove the SLO above if records can wait in partitions for several minutes.

Track end-to-end event age and actual processing status, combining listener duration, retries, lag, and DLT.

## 16. Micrometer tags and cardinality cost

`MeterRegistry` manages meters by **name + tags**. Each distinct combination of tags can become a separate time series in the monitoring backend.

Suppose:

- 20 listener IDs/children.
- 2 result values.
- 8 exception classes.
- 3 environments.
- 10 pod instances.

The theoretical combinations can reach 20 × 2 × 8 × 3 × 10 = 9,600 series, before histogram buckets. In practice not all combinations appear, yet the cost can be substantial.

Adding `orderId` as a tag with millions of values can cause cardinality to explode.

### 16.1 Rule: tags are bounded dimensions

Reasonable tags:

- `service`: `orders-worker`.
- `environment`: `prod`.
- `listener`: `orders-projection`.
- `topic`: `orders.created`, when the topic set is finite.
- `result`: `success`/`failure`.
- `exception` category or bounded class.

Unsuitable tags:

- raw exception message.
- business entity ID.
- event UUID.
- offset.
- high-cardinality Kafka message keys.
- user email, phone, JWT, token.

### 16.2 Use MeterFilter when needed

Micrometer supports `MeterFilter` to deny or transform meters/tags according to registry policy. For example, you can cap the number of allowed tag values for a tag on a meter.

~~~java
@Bean
MeterFilter kafkaListenerCardinalityGuard() {
    return MeterFilter.maximumAllowableTags(
        "spring.kafka.listener",
        "name",
        100,
        MeterFilter.deny()
    );
}
~~~

This is an illustrative guard; it does not replace proper naming design. If the threshold of 100 is exceeded, new series may be denied, leaving dashboards incomplete. Set up metrics/alerts for exceeding the cardinality budget and base the limit on actual listener counts.

### 16.3 Histograms multiply series

Histogram buckets multiply series counts across tags. Enabling histograms for every listener, every exception tag, and every pod can increase costs dramatically.

Enable percentile histograms selectively, or aggregate by domain when sufficient for SLOs. Verify storage/cost before rolling out broadly.

## 17. Misleading configurations and symptoms

### 17.1 Listener timers enabled but no metrics visible

Possible causes:

- Appropriate Micrometer dependency is missing.
- No registry exists or the registry is not used by the exporter.
- The listener has never received a record or recorded an invocation.
- A different container factory is being used by the listener.
- `micrometerEnabled=false` was overridden by a customizer.
- `observationEnabled=true` changed the instrumentation path.
- A `MeterFilter` dropped or altered the meter.
- Prometheus endpoint is not exposed/scraped.
- Query confuses the logical meter name with the Prometheus metric name.

### 17.2 Prometheus shows the metric without histograms

Timer `count`/`sum` may be present while `_bucket` is absent because histograms were not enabled. Do not try to compute p95 from `_sum`/`_count`.

### 17.3 Metric `name` tag differs from `@KafkaListener.id`

With concurrency greater than one, the `name` tag can reflect child containers. Inspect `/actuator/metrics/spring.kafka.listener` and actual tags before writing dashboard regexes.

### 17.4 Listener timer failure is low while DLT spikes

Deserialization may be failing before the listener, or retries/recovery are happening at the container layer. The timer is insufficient to reflect those cases. Add a dedicated DLT publisher metric.

### 17.5 Listener timer success is high while DB has no data

The listener may be catching and swallowing exceptions, dispatching async tasks and returning before completion, or rolling back transactions after the invocation. Use business counters, transaction results, and lifecycle tests.

### 17.6 Disabling micrometerEnabled and assuming all Kafka metrics stop

Kafka client metrics or custom meters may still exist. If Observation is enabled, metrics from `ObservationRegistry` may still appear. Identify which instrumentation source produces each meter.

## 18. Choosing exception tags

A failure timer can carry a simple exception class, for example:

~~~text
exception=TransientDataAccessException
exception=IllegalArgumentException
exception=SerializationException
~~~

This helps group errors, though not every failure originates inside the listener. Combine with logs for root-cause analysis.

A wrapper like `ListenerExecutionFailedException` may appear depending on the error-catching layer and implementation. Do not assert that the `exception` tag is always the true root cause without checking metric output for your version.

If the application has hundreds of exception subclasses, the `exception` tag can inflate cardinality. Classify errors into stable groups in a custom metric:

~~~text
error_class=transient_dependency
error_class=invalid_data
error_class=business_conflict
error_class=unexpected
~~~

Never put `exception.getMessage()` into a tag; messages often contain dynamic IDs, URLs, or sensitive data.

### 18.1 Custom Listener Error metrics can be used

Service example:

~~~java
public class OrderProcessingMetrics {

    private final MeterRegistry registry;

    public OrderProcessingMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordFailure(String category) {
        registry.counter(
            "orders.processing.failure",
            "category", category
        ).increment();
    }
}
~~~

`category` must come from an application-defined enum/finite value set. Do not pass arbitrary raw exception classes/messages without a cardinality policy.

## 19. Designing operationally useful dashboards

A good listener dashboard should include four groups:

**Processing group:** listener invocation throughput, success/failure rate, average duration, p95/p99 when histograms are available.

**Consumer group:** group lag per partition, poll/rebalance events, pause state, assignment, records consumed rate.

**Recovery group:** retry attempts, retries exhausted, recoverer failures, DLT publish rate, and DLT oldest age.

**Business group:** valid events count, events with applied business effects, duplicate detection, end-to-end age, and SLA breaches.

### 19.1 Panel examples

| Panel | Data | Question |
|---|---|---|
| Orders listener attempts/s | `spring.kafka.listener` timer count | Is the listener processing? |
| Orders listener p95 | Timer histogram | Is the listener slower than normal? |
| Failure ratio by listener | `result=failure` | Which listener has errors? |
| Consumer lag by partition | Group lag metrics | Which topic/partition has backlog? |
| Pause duration | Container pause events/metric | Is there prolonged backpressure? |
| Retry exhausted | Error handler metric | Are records moving to recovery? |
| DLT publish failures | Recoverer/producer metric | Are failed records durably quarantined? |
| Business completion age | Application instrumentation | Are business SLAs being met? |

### 19.2 Do not alert on a single metric alone

Listener success throughput = 0 for a period may just mean the topic has no new records. Do not page an outage if the producer rate is also 0 and lag is 0.

A more meaningful alert:

~~~text
Consumer lag is increasing
AND producer rate > 0
AND listener completion throughput is low
FOR a sufficiently long duration
~~~

If high error rates or prolonged pause durations occur at the same time, the alert carries additional root-cause context.

## 20. A practical Spring Boot configuration

Suppose the application uses Spring Boot Actuator and Prometheus:

~~~groovy
dependencies {
    implementation("org.springframework.kafka:spring-kafka")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("io.micrometer:micrometer-registry-prometheus")
}
~~~

Listener factory:

~~~java
@Configuration
public class KafkaMetricsConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(2);

        ContainerProperties props =
            factory.getContainerProperties();

        props.setMicrometerEnabled(true);
        props.setObservationEnabled(false);

        props.setMicrometerTags(
            Map.of(
                "domain", "orders",
                "pipeline", "projection"
            )
        );

        return factory;
    }
}
~~~

Prometheus exposure via Actuator must be configured per your Spring Boot version and secured. An effective verification flow:

1. Start the application with Kafka and a test producer.
2. Send several `orders` records.
3. Wait for the listener to actually be invoked.
4. Check `/actuator/metrics/spring.kafka.listener`.
5. Check `/actuator/prometheus` for the corresponding series.
6. Verify the monitoring target is scraping.
7. Group by `name`/`result`/`exception` and custom tags.
8. Trigger a controlled test failure to inspect the `result=failure` metric.
9. Ensure dashboards do not miscount retries as unique records.

### 20.1 Do not expose Actuator unprotected

Prometheus and metrics endpoints can reveal service names, internal endpoints, exception classes, topology, or runtime details. Production requires:

- Network segmentation or service mesh policies.
- Appropriate authentication/authorization.
- Exposing only needed endpoints.
- Controlling raw tag values.
- Keeping PII out of tags.
- Monitoring scrape load and cardinality.

Metrics collection is also part of the operational system that requires security.

## 21. Testing micrometerEnabled with integration tests

Unit tests that call `@KafkaListener`-annotated methods directly bypass the Spring Kafka listener container, so they do not verify container timer instrumentation.

Use Embedded Kafka or Testcontainers Kafka, a real Spring `ApplicationContext`, and an inspectable `MeterRegistry`.

### 21.1 Success test

1. Configure the listener factory with `micrometerEnabled=true`.
2. Create a `MeterRegistry` for testing, e.g. `SimpleMeterRegistry`.
3. Send a valid record.
4. Wait for `@KafkaListener` to actually process the record.
5. Find the `spring.kafka.listener` meter in the registry by actual tags.
6. Assert invocation count increases.
7. Assert duration has a valid value.
8. Do not assert exact millisecond latency, as CI has scheduler jitter.

### 21.2 Failure test

1. Send a record triggering the listener to throw an exception.
2. Configure finite retries/recovery so the test does not hang.
3. Wait for the handler/recovery to finish.
4. Assert the failure timer is recorded per actual outcome.
5. Reconcile attempt count with retry policy.
6. Do not conclude DLT succeeded merely because the failure timer increased.

### 21.3 Disabled micrometerEnabled test

1. Use a separate factory with `setMicrometerEnabled(false)`.
2. Send records through that listener.
3. Confirm legacy listener timers are not recorded for the disabled factory, per registry/test setup.
4. Confirm custom metrics or Kafka client metrics may still exist if enabled independently.

If using Observation, test that instrumentation path separately to avoid misinterpreting a metric of the same name created by Observation.

### 21.4 Static tags test

1. Enable `setMicrometerTags` with `domain=orders`.
2. Send a record.
3. Verify the meter has tag `domain=orders`.
4. Confirm other listeners are not accidentally given that tag.
5. Inspect child container names when `concurrency>1`.

### 21.5 Cardinality test

1. Send multiple records with different `eventId` values.
2. Verify meter series count does not grow per `eventId`.
3. If using `micrometerTagsProvider`, verify tags belong to the whitelist.
4. Measure registry memory footprint under load.
5. Confirm series limits match the metrics backend budget.

### 21.6 Retry and batch test

- Record listener retried twice: timer count can reflect multiple invocations.
- Batch listener one invocation containing many records: timer count does not equal record count.
- Deserialization failure before listener: inspect separate error metrics and DLT.
- Transaction abort after listener returns: monitor transaction outcome, not just timer success.

## 22. Integration test pattern with SimpleMeterRegistry

A test can create a `MeterRegistry` to read metrics emitted by the application. When using Spring Boot, ensure **the registry used by listener instrumentation** actually connects to the test registry. If your Spring Kafka version uses the global Micrometer registry, the test config must wire or clean the global registry properly.

Illustrative assertion concept:

~~~java
@Test
void listenerTimerShouldRecordSuccessfulInvocation() {
    // Arrange: application context with Micrometer registry
    // and real Kafka listener container.

    producer.send("orders", "order-1001", validOrderPayload);

    await().atMost(Duration.ofSeconds(10))
        .untilAsserted(() -> {

            Timer timer = registry.find("spring.kafka.listener")
                .tag("result", "success")
                .timer();

            assertThat(timer).isNotNull();
            assertThat(timer.count()).isGreaterThan(0);
        });
}
~~~

This is directional pseudocode; add producer setup, `@SpringBootTest`/Testcontainers, imports, and actual tags matching your version. Do not copy a snippet verbatim and expect it to compile without producer, registry, or listener factory beans.

### 22.1 Do not let tests pollute the global registry

If tests run in the same JVM and share `Metrics.globalRegistry`, meters from a prior test can make subsequent tests falsely pass or flake.

You can:

- Create an isolated `SimpleMeterRegistry`.
- Register/unregister registries properly per lifecycle.
- Use unique listener IDs/topics for tests.
- Read the baseline count before sending a record.
- Assert **delta count** rather than just `count > 0`.
- Clean up listeners/registry after the test.

### 22.2 Assertions should measure behavior, not hardcode wrong tags

If a concurrent container tags `name` as `orders-projection-0` instead of `orders-projection`, an equality assertion on the parent ID can fail even when instrumentation works properly.

First inspect registry meter IDs and tags in tests, then pick predicates matching the version's naming convention. This is equally important for production monitoring queries.

## 23. Symptom: "spring.kafka.listener metric is missing"

When dashboards show no data:

1. Confirm the listener actually received and processed records, not just that the container is `RUNNING`.
2. Confirm which `containerFactory` `@KafkaListener` is using.
3. Check the effective `ContainerProperties.micrometerEnabled` on the active factory/container.
4. Check that the Micrometer dependency is on the runtime classpath.
5. Check `observationEnabled` as it can change the instrumentation path.
6. Confirm `MeterRegistry` exists and the exporter is enabled.
7. Check Actuator's `metrics` endpoint for the logical meter.
8. Check the `prometheus` endpoint for exported series.
9. Check scrape target, network/security, and Prometheus last scrape status.
10. Check `MeterFilter`, common tags, and naming conventions.
11. Check for unexpected tags, especially child suffixes on `name`.
12. Send a test record to trigger a new invocation and compare the count delta.

Do not turn on `DEBUG` logging for the entire Kafka client just to find one metric; separate **instrumentation**, **registry**, **exporter**, and **scrape** to isolate the issue.

## 24. Symptom: "timer is very fast yet business processing is slow"

For example, timer p95 is only 10 ms, yet order projection completes 30 seconds later.

Possible reasons:

- The listener submits an async job and returns.
- Kafka lag makes events wait long before the listener is invoked.
- The business transaction commits after the listener method.
- Retry/backoff and DLT account for most of total latency.
- The consumer only times the invocation, not downstream completion.
- Timing metrics are mixed across different listeners or batch processing.
- Some errors occur before the listener and do not show up in the timer.

Procedure:

1. Identify `eventId` and Kafka append timestamp.
2. Identify listener start and end times.
3. Identify business side-effect completion timestamp.
4. Check lag/pause/retries.
5. Check the async executor queue.
6. Verify the timer is measuring the right listener.
7. Add appropriate business completion metrics or tracing spans.

Do not try to force `micrometerEnabled` to measure stages outside the listener timer's scope.

## 25. Symptom: "metrics increment more than the number of records"

If listener timer count exceeds the number of records sent by the producer, this can be normal because:

- Blocking retries invoke the listener multiple times.
- Consumer restarts after side effects but before offset commit.
- Group rebalance causes records to be redelivered.
- Manual ack has not completed.
- Batch retry re-runs a set of records.
- Multiple listeners subscribe to the same topic in different groups.
- A dashboard sums both success and failure attempts.

To count unique records, use `eventId` or `topic-partition-offset` with proper deduplication semantics, but **never use eventId as a metric tag**. You can increment a business completion counter only when idempotent storage confirms the event has not been processed previously.

## 26. When should micrometerEnabled be disabled?

There are several valid situations:

- The workload uses Micrometer Observation and is migrating metrics.
- Tracing/Observation already supplies needed data and duplicate timers should be avoided.
- A specialized listener has very high traffic and measured instrumentation cost must be reduced.
- The monitoring backend is experiencing cardinality explosion from tags/naming.
- You want to temporarily isolate a listener group from automatic timers to measure via different instrumentation.

However, never disable it just because the metric "shows too many errors." Disabling metrics blinds you to the signal; it does not make business errors disappear.

Before disabling, you must:

1. Identify which dashboards/alerts depend on `spring.kafka.listener`.
2. Confirm replacement metrics are already working.
3. Measure instrumentation cost if performance is the reason.
4. Announce the metric schema change to operations.
5. Test in staging/canary.
6. Monitor after rollout.

## 27. Phased implementation recommendation

A controlled rollout approach:

### Phase 1: listener timers

Enable `micrometerEnabled` on the factories to measure, verifying timer count and duration flow through `MeterRegistry`. Use low-cardinality static tags.

### Phase 2: consumer/client metrics

Add Kafka client metrics and lag monitoring. Ensure dashboards reflect group, topic, and partitions.

### Phase 3: error and recovery

Measure retries, DLT publish outcomes, deserialization errors, commit failures, and rebalances. Separate listener failures from final business outcomes.

### Phase 4: end-to-end SLO

Instrument event age, business completion, duplicate detection, and offset progression. Alert on SLOs rather than a single listener latency threshold.

### Phase 5: tracing when needed

If producer-consumer correlation or cross-service tracing is needed, evaluate `observationEnabled` and Micrometer Tracing. Plan metric/tag migrations so existing dashboards do not break.

You do not need to deploy everything at once. However, define each layer's boundaries so you never draw wrong conclusions from a single metric.

## 28. Common misconceptions

**"micrometerEnabled=true automatically enables Prometheus."** No. You need a registry/exporter, Actuator endpoint, and scrape config.

**"micrometerEnabled defaults to false."** Not necessarily. In versions supporting listener timers, the default is typically `true` when Micrometer is available.

**"Timer count equals unique Kafka records."** No. Retries/redeliveries increment count; batch listener count measures invocations.

**"Timer success means the offset committed."** No. A successful listener invocation is different from commit/transaction outcomes.

**"Timer failures equal records routed to DLT."** No. Retry attempts and recovery are distinct.

**"The timer also measures Kafka lag."** No. Lag requires Kafka client/broker/group monitoring.

**"Enabling Observation and Timer always yields two identical metric sets."** No. The framework may disable legacy timers when Observation is enabled; inspect runtime output.

**"Disabling micrometerEnabled makes all Kafka metrics disappear."** No. Client metrics and custom metrics are independent.

**"One record batch = one timer count."** No. One batch invocation can contain many records.

**"An async listener will be timed until the task completes."** Not by default if the method returns before task completion.

**"Adding eventId to tags makes tracking more accurate."** Very risky. It creates high-cardinality metrics; use logs/traces or other storage.

**"Having p95 timer is enough for end-to-end SLO."** No. You must account for time records wait in Kafka, retries, and downstream completion.

**"Every deserialization error is recorded by the timer."** No. Some errors happen before listener invocation.

**"Missing metric proves the listener is not running."** No. It may be a registry, exporter, scraping, filter, or configuration issue.

## 29. Implementation and operations checklist

**Container configuration**

- [ ] Identify the exact `ConcurrentKafkaListenerContainerFactory` for each `@KafkaListener`.
- [ ] Know the effective `micrometerEnabled` and `observationEnabled` settings.
- [ ] Micrometer dependency and `MeterRegistry` are present.
- [ ] Avoid duplicate instrumentation from auto-configuration and custom wiring.
- [ ] Establish naming conventions for parent/child listener IDs.
- [ ] Distinguish record vs. batch listeners when reading counts.

**Metrics and tags**

- [ ] Confirm `spring.kafka.listener` meter is recorded in the registry.
- [ ] Verify actual `name`/`result`/`exception` tags per framework version.
- [ ] Static/dynamic tags have bounded cardinality.
- [ ] Never attach `eventId`, `orderId`, `offset`, or PII to metric tags.
- [ ] Enable histograms selectively when p95/p99 is needed.
- [ ] Prometheus scrape has appropriate security and resource budgets.

**Reliability**

- [ ] Never treat listener success as business commit success.
- [ ] Monitor retries, DLT, deserialization, and transaction failures.
- [ ] Have Kafka client metrics and consumer lag monitoring in place.
- [ ] Have idempotency/business completion metrics where needed.
- [ ] Have end-to-end SLOs on event age or business completion.
- [ ] Alerts include traffic, lag, and duration conditions to reduce false positives.

**Verification**

- [ ] Tested success/failure timers with a real container.
- [ ] Tested `micrometerEnabled=false`.
- [ ] Tested static tags and concurrency child suffixes.
- [ ] Tested that retry count differs from unique record count.
- [ ] Tested batch invocation counts.
- [ ] Tested registry/exporter/scrape end-to-end.
- [ ] Checked `observationEnabled` impact during migration.
- [ ] Measured cardinality and histogram overhead under load.

## 30. Conclusion

**micrometerEnabled** is the switch for Spring Kafka's **Micrometer listener timers**. When enabled with Micrometer properly configured, it measures listener invocation counts, invocation duration, and distinguishes `success`/`failure` outcomes via tags. It is an essential observability layer for catching slow or exception-heavy listeners, yet **it does not measure consumer lag, does not guarantee offsets committed, and does not prove business work completed exactly once**.

A production deployment must distinguish Timers from Kafka client metrics, business metrics, and Micrometer Observation; protect metric cardinality; configure registries/exporters properly; and verify behavior in an environment with real Kafka listener containers. Setting `micrometerEnabled` on the right factory is the first step, while reliable operations come from combining listener timing with lag, retries, DLT, transaction outcomes, and end-to-end SLOs.


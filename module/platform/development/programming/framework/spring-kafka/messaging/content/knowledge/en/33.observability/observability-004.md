# Micrometer metrics for Kafka

Micrometer provides a unified API for collecting metrics in Spring applications. When combined with Spring Kafka, an application can measure record send duration via `KafkaTemplate`, processing duration in `@KafkaListener`, Kafka producer/consumer client state, and custom business metrics produced by the application itself.

Metrics help answer operational questions such as: how many records per second does the producer send, how long does the listener take to process, is the consumer lagging, which topic has rising errors, and did throughput drop after a deployment? Spring Kafka also supports Micrometer Observation to combine metrics with tracing when the application has an `ObservationRegistry` and an appropriate tracing bridge.

## 1. Observability consists of metrics, logs, and traces

The three signal types complement one another:

| Signal | Question answered | Examples in Kafka |
| --- | --- | --- |
| Metrics | How is the system behaving overall? | Records sent/consumed rate, listener latency, consumer lag, error rate |
| Logs | What happened during a specific execution? | Event ID, topic, partition, offset, exception |
| Traces | Which services did a request/event traverse and where was time spent? | HTTP request → publish Kafka → consume → database call |

Micrometer primarily provides the metrics API and Observation API. It does not replace business logging or a distributed tracing backend. When Observation is enabled, the application can emit both spans and metrics from the same observation if a registry/bridge is configured.

For example: rising consumer lag is a metrics signal; logs keyed by `eventId` locate the failing record; traces identify whether time was spent in the listener, database, or a downstream service.

## 2. Sources of metrics in Spring Kafka

Metrics can be grouped into three categories:

1. **Spring Kafka operation metrics/observations:** duration and outcomes of sending via `KafkaTemplate`, and duration of listener record or batch processing.
2. **Kafka client metrics:** internal metrics exposed by Kafka producer/consumer clients, such as request latency, fetch rate, records consumed, rebalances, and per-partition lag.
3. **Business metrics:** orders processed, rejected events, business execution duration, retry counts, or records routed to a DLT.

```mermaid
flowchart TD
    A[Spring Kafka application] --> B[KafkaTemplate]
    A --> C[@KafkaListener containers]
    A --> D[Business code]
    B --> E[Template metrics / Observation]
    C --> F[Listener metrics / Observation]
    B --> G[Kafka producer client metrics]
    C --> H[Kafka consumer client metrics]
    D --> I[Custom Counter / Timer / Gauge]
    E --> J[Micrometer MeterRegistry]
    F --> J
    G --> J
    H --> J
    I --> J
    J --> K[Prometheus / OTLP / monitoring backend]
```

Not every Spring Kafka version enables the same instrumentation in the same way. Framework version, Micrometer on the classpath, and timer/observation configuration determine which metrics are produced. Check your actual version and registered meters instead of assuming metric names are identical across applications.

## 3. Adding Micrometer and Actuator

In Spring Boot applications, Actuator is commonly used to manage health/metrics endpoints along with a registry to export data to a backend.

Example Maven dependencies:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Spring Boot dependency management should control the Micrometer version compatible with Boot. Avoid pinning a different `micrometer-core` version from the one managed by Spring Boot without a specific reason.

If not using Spring Boot, declare an appropriate `MeterRegistry` and configure the corresponding exporter/registry. Spring Kafka integrates with Micrometer when the required dependencies and registry are present.

## 4. Exposing metrics for Prometheus

With the Prometheus registry, you can expose the `/actuator/prometheus` endpoint:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when_authorized
  prometheus:
    metrics:
      export:
        enabled: true
```

After the application starts, inspect the endpoints:

```text
GET /actuator/health
GET /actuator/metrics
GET /actuator/metrics/{metric-name}
GET /actuator/prometheus
```

`/actuator/metrics` lists meter names; `/actuator/metrics/{metric-name}` displays the meter and its available tags; `/actuator/prometheus` exports data in Prometheus scrape format. Expose only necessary endpoints and protect them using network policies, authentication, or a separate management port.

Example Prometheus scrape configuration:

```yaml
scrape_configs:
  - job_name: spring-kafka-messaging
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - orders-service:8080
          - billing-service:8080
```

In production, use service discovery rather than a static host list if the environment uses autoscaling. Metrics endpoints can reveal internal operational details; do not expose them publicly on the Internet.

## 5. Metrics and Observation for KafkaTemplate

`KafkaTemplate` sends records and can report send duration, outcomes, and exceptions. In Spring Kafka versions supporting Micrometer timers, the template can record a timer for send operations. Versions supporting Observation allow enabling observation on the template to integrate with `ObservationRegistry`.

In Spring Boot versions supporting this property, enable observation for the template:

```yaml
spring:
  kafka:
    template:
      observation-enabled: true
```

When creating `KafkaTemplate` manually, enable it using the corresponding API:

```java
import com.example.messaging.event.OrderEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;

@Bean
public KafkaTemplate<String, OrderEvent> orderKafkaTemplate(
        ProducerFactory<String, OrderEvent> producerFactory
) {
    KafkaTemplate<String, OrderEvent> template =
            new KafkaTemplate<>(producerFactory);
    template.setObservationEnabled(true);
    return template;
}
```

Observation captures publish duration and outcome, while also creating tracing spans if the application configures a tracing bridge/exporter. Spring Kafka's default observation name can be used to look up the corresponding timer in the registry; the Prometheus meter name is normalized by the registry.

If using legacy Micrometer timer APIs instead of Observation, check `micrometerEnabled` and the `setMicrometerEnabled`/tags APIs for your Spring Kafka version. Do not unintentionally enable duplicate instrumentation; pick the mechanism suited to your version and verify actual registered meters.

## 6. Metrics and Observation for @KafkaListener

Listener containers can record listener processing duration and outcomes. In Spring Boot versions supporting listener observation configuration:

```yaml
spring:
  kafka:
    listener:
      observation-enabled: true
```

For manually configured container factories, enable observation on `ContainerProperties`:

```java
import com.example.messaging.event.OrderEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory
        ) {
    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    factory.getContainerProperties().setObservationEnabled(true);
    return factory;
}
```

For record listeners, instrumentation measures individual listener invocation duration. For batch listeners, duration usually reflects batch processing; interpret the metric according to the configured listener type.

When Observation is enabled, listeners can create spans tied to message processing. Trace context propagation through Kafka headers depends on observation/tracing instrumentation and propagator configuration; do not assume trace context is always present simply by adding Actuator.

## 7. Native Kafka client metrics

Kafka producers and consumers maintain their own metrics provided by the Kafka client. They provide visibility below the listener level, covering fetches, requests, networking, batching, and rebalances.

Commonly tracked producer metrics:

| Kafka client metric | Meaning |
| --- | --- |
| `record-send-rate` | Rate of records sent |
| `record-error-rate` | Rate of record sends encountering errors |
| `request-latency-avg` / `request-latency-max` | Request latency to the broker |
| `record-queue-time-avg` | Time records wait in the producer before being sent |
| `batch-size-avg` | Average send batch size |
| `buffer-available-bytes` | Available producer buffer capacity |
| `bufferpool-wait-time-total` | Time the producer waits for buffer pool memory |
| `outgoing-byte-rate` | Outgoing byte rate |

Commonly tracked consumer metrics:

| Kafka client metric | Meaning |
| --- | --- |
| `records-consumed-rate` | Rate of records consumed |
| `bytes-consumed-rate` | Incoming byte rate |
| `fetch-rate` / `fetch-latency-avg` | Fetch rate and latency |
| `records-lag-max` | Maximum per-partition lag in the corresponding metric set |
| `assigned-partitions` | Number of partitions assigned to the consumer |
| `commit-latency-avg` | Offset commit latency |
| `heartbeat-rate` | Heartbeat frequency |
| `rebalance-total` | Total number of rebalances that occurred |

Native Kafka client metric names may have their formatting/tags transformed when exported via Micrometer. Some metrics are recorded per producer/consumer instance or per partition; do not sum them arbitrarily without understanding their measurement scope.

## 8. Registering KafkaClientMetrics for producers and consumers

Micrometer provides the `KafkaClientMetrics` binder to bind Kafka client metrics to `MeterRegistry`. Spring Kafka also provides listeners that automatically bind/unbind metrics when factories create and close producers/consumers.

Example with `MicrometerConsumerListener` and `MicrometerProducerListener`:

```java
package com.example.messaging.config;

import com.example.messaging.event.OrderEvent;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.MicrometerConsumerListener;
import org.springframework.kafka.core.MicrometerProducerListener;

@Configuration
public class KafkaClientMetricsConfiguration {

    @Bean
    public MicrometerConsumerListener<String, OrderEvent>
            consumerMetricsListener(MeterRegistry registry) {
        return new MicrometerConsumerListener<>(registry);
    }

    @Bean
    public MicrometerProducerListener<String, OrderEvent>
            producerMetricsListener(MeterRegistry registry) {
        return new MicrometerProducerListener<>(registry);
    }
}
```

The listeners must be registered on the right factories:

```java
consumerFactory.addListener(consumerMetricsListener);
producerFactory.addListener(producerMetricsListener);
```

If Spring Boot already registers Micrometer listeners automatically on auto-configured factories in your version, do not register duplicates. For custom factories, check existing integration and attach listeners if needed. Exact class names and APIs must match your application's Spring Kafka/Micrometer version.

Another approach is creating `KafkaClientMetrics` from a Kafka `Producer`/`Consumer` instance and calling `bindTo(registry)`. When binding directly, manage the binder lifecycle and unbind/close it when the client closes; avoid creating a binder for an already-closed client or binding the same client multiple times.

## 9. Measuring business processing time with Timer

Default metrics report listener invocation duration, but sometimes you need to measure a specific business step such as writing an invoice or calling a Pricing service.

```java
package com.example.orders.service;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.function.Supplier;
import org.springframework.stereotype.Service;

@Service
public class OrderProcessingMetrics {

    private final MeterRegistry registry;

    public OrderProcessingMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public <T> T recordProcessing(String result, Supplier<T> operation) {
        return Timer.builder("orders.kafka.processing")
                .description("Business processing time for Order event")
                .tag("result", result)
                .register(registry)
                .record(operation);
    }
}
```

`Timer.record(Supplier<T>)` measures the execution time of the operation and returns the supplier's result. When code throws an exception, the timer still records the invocation duration; design the `result` tag to distinguish success/error without putting dynamic exception messages into tags.

Usage example:

```java
package com.example.orders.service;

import com.example.orders.metrics.OrderProcessingMetrics;

OrderResult result = metrics.recordProcessing(
        "success",
        () -> orderService.apply(event)
);
```

If you need to measure both success and failure accurately, use `Timer.Sample` and stop the timer in `finally` with the resolved result tag. Do not create a new Timer per event; `Timer.builder(...).register(registry)` returns the existing meter registered with the same name/tag set.

## 10. Counter for event counts and errors

A `Counter` is suitable for cumulative counts such as successfully processed events, rejected events, or DLT deliveries.

```java
package com.example.orders.metrics;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class OrderEventMetrics {

    private final Counter processed;
    private final Counter failed;

    public OrderEventMetrics(MeterRegistry registry) {
        this.processed = Counter.builder("orders.kafka.processed")
                .description("Number of Order events processed successfully")
                .register(registry);
        this.failed = Counter.builder("orders.kafka.failed")
                .description("Number of Order events failed to process")
                .register(registry);
    }

    public void markProcessed() {
        processed.increment();
    }

    public void markFailed() {
        failed.increment();
    }
}
```

Counters increase monotonically within a process lifecycle; when the process restarts, in-memory values reset. Prometheus stores the time series and handles counter resets when querying with `rate()`/`increase()`.

Increment counters at the exact business boundary: for example, increment `processed` only after side effects succeed. If a listener can receive the same record again, invocation count and unique event count are two different concepts. Use clear metric names so listener execution counts are not misinterpreted as unique events.

## 11. Gauge for pending state

A `Gauge` measures a value that can go up or down, such as the number of tasks sitting in an internal queue or pending request-reply operations.

```java
package com.example.orders.metrics;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class PendingWorkMetrics {

    private final AtomicInteger pending = new AtomicInteger();

    public PendingWorkMetrics(MeterRegistry registry) {
        Gauge.builder("orders.kafka.pending", pending, AtomicInteger::get)
                .description("Number of pending tasks awaiting processing in the application")
                .register(registry);
    }

    public void started() {
        pending.incrementAndGet();
    }

    public void completed() {
        pending.decrementAndGet();
    }
}
```

Keep a strong reference to the object observed by the `Gauge`; if the object is garbage collected, the Gauge may stop reporting expected values. Update the gauge on every completion path, including exceptions and cancellations, to prevent the pending count from growing indefinitely.

Do not use a Gauge to count total processed events; a Counter is better suited for cumulative values.

## 12. DistributionSummary for batch size

If a listener receives batches, `DistributionSummary` helps measure the distribution of record counts per batch:

```java
package com.example.audit.metrics;

import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class AuditBatchMetrics {

    private final DistributionSummary batchSize;

    public AuditBatchMetrics(MeterRegistry registry) {
        this.batchSize = DistributionSummary.builder("audit.kafka.batch.size")
                .description("Number of records in each listener batch")
                .baseUnit("records")
                .register(registry);
    }

    public void recordBatch(int size) {
        batchSize.record(size);
    }
}
```

From the distribution you can observe average batch size, max, and histograms if configured on the registry. Combine this with the listener processing timer to see whether large batches increase latency.

## 13. Consumer lag and partition-level metrics

Consumer lag is the distance between a partition's newest record position and the consumer group's progress. Continuously growing lag can indicate that the consumer is not keeping up with the producer.

Lag should be observed per partition and per consumer group. The Kafka client exposes consumer/partition-level lag metrics in some versions, but those do not always replace aggregated group lag metrics. You can use a Kafka exporter, JMX exporter, or Kafka platform monitoring tools to collect group lag and log end offsets.

The CLI helps inspect lag during investigations:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-service
```

The `CURRENT-OFFSET`, `LOG-END-OFFSET`, and `LAG` columns reveal which partition is falling behind. Combine this with application metrics such as processing time, records consumed rate, and downstream latency to locate the root cause.

Lag is not always an error. A traffic burst can cause lag to spike briefly and then drain. Monitor trends, lag growth rate, and recovery time instead of alerting solely whenever lag is non-zero.

## 14. Tags and cardinality

Tags allow grouping metrics by attributes with a bounded value set, such as topic, listener ID, group ID, result, or exception class.

Suitable tags:

- `topic=orders.events`
- `group=orders-service`
- `listener=ordersListener`
- `result=success|failure`
- `exception=TimeoutException`

Avoid using values that vary per record as tags:

- `eventId`
- `orderId`
- `customerId`
- `correlationId`
- email or user ID
- dynamic exception messages

Every tag combination creates a time series. Adding `orderId` as a tag can cause series count to scale with order volume, driving high RAM, CPU, and storage usage in Prometheus/Micrometer.

Use only the exception class or standardized error category; never use stack traces/messages as tags. For dynamic topics or large tenant counts, evaluate cardinality before placing them in metric tags.

## 15. Custom Observation conventions and trace context

Observation lets you attach contextual metadata to an operation. Spring Kafka provides default conventions and APIs to customize conventions/tags as needed.

Conceptual example of setting a custom convention:

```java
template.setObservationConvention(customKafkaTemplateObservationConvention);
```

Conventions should add low-cardinality key-values such as business flow name or standardized event type. Do not put `eventId` or `orderId` into low-cardinality tags. If unique values are needed for investigations, place them in logs or trace span events/attributes with appropriate limits rather than turning them into metric labels.

When tracing is configured, trace context can be propagated via Kafka headers to connect producer spans and consumer spans. Verify propagation on your exact Spring Kafka, Micrometer Observation, and tracing bridge versions; if modifying headers manually, do not overwrite framework-managed trace context.

## 16. Basic PromQL for Kafka application metrics

For the custom Counter `orders.kafka.processed`, Prometheus typically normalizes the name to `orders_kafka_processed_total`. You can query:

```promql
sum(rate(orders_kafka_processed_total[5m]))
```

To inspect error processing rate:

```promql
sum(rate(orders_kafka_failed_total[5m]))
```

If the Timer `orders.kafka.processing` is exported as a histogram, you can compute p95:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(orders_kafka_processing_seconds_bucket[5m])
  )
)
```

Exact metric names depend on the registry, naming convention, and histogram configuration. Inspect `/actuator/prometheus` to verify real metric names before writing dashboards or alerts.

To export histogram buckets for a Timer in Spring Boot, you can enable percentile histograms by meter name:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        orders.kafka.processing: true
```

Without enabling histograms (or configuring appropriate percentiles), `_bucket` metrics may not be exported and the `histogram_quantile` query above will have no data. Histograms create additional time series; enable them only for timers requiring percentile analysis and control tag counts.

Simple alert example for error rate:

```promql
sum(rate(orders_kafka_failed_total[5m])) > 1
```

In production, compare error rate against throughput or use an error ratio rather than an absolute threshold when load fluctuates heavily.

## 17. What should a dashboard include?

A Kafka service dashboard can be organized into rows:

| Group | Suggested panels |
| --- | --- |
| Producer | Send rate, send error rate, request latency, outgoing bytes |
| Consumer | Records consumed rate, fetch latency, assigned partitions, rebalances |
| Listener | Processing duration p50/p95/p99, success/failure count, batch size |
| Lag | Total consumer group lag and per-partition lag |
| Retry/DLT | Retry rate, DLT publish rate, DLT backlog |
| Business | Orders processed, payments rejected, inventory update failures |
| Runtime | CPU, heap, GC pauses, thread count, connection pool usage |

The dashboard should offer filters by service, environment, topic, and consumer group. Avoid creating dashboards with thousands of series keyed by event ID or entity ID.

## 18. Common pitfalls when using Micrometer with Kafka

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| No Kafka metrics visible | Missing registry/Micrometer dependency or instrumentation not enabled | Check dependencies, `MeterRegistry`, and template/container config |
| Listener timer exists but no client metrics | Missing `KafkaClientMetrics`/factory listener binding or Boot version does not auto-configure it | Check producer/consumer factories and Micrometer listeners |
| Duplicate metrics | Both legacy timers and Observation/custom timers enabled for the same operation | Check meter names and choose the right instrumentation |
| Prometheus cannot scrape | Endpoint not exposed, wrong port/path, or network policy | Check Actuator exposure and scrape target |
| Abnormal cardinality growth | Dynamic IDs used as tags | Remove event/entity IDs from tags; use logs/traces |
| Consumer lag not shown | Only listener timer enabled, no group lag exporter/client metric | Add Kafka exporter/JMX or a group lag source |
| Timer lacks histogram | Percentile histogram not enabled or registry does not export buckets | Configure histograms as needed and inspect the endpoint |
| Gauge always 0 | Gauge observes an unreferenced object or is updated incorrectly | Keep object alive and verify increment/decrement paths |
| Metrics do not match unique records | Counter increments per invocation, including redeliveries | Distinguish invocation count from unique business events |
| Tracing does not link producer and consumer | Observation/tracing bridge or propagation not configured | Check registry, propagator, and Kafka headers |

## 19. Testing metrics

You do not need a real Kafka broker for every metrics unit test. You can use `SimpleMeterRegistry` to test custom Counters, Timers, Gauges, and DistributionSummaries.

Example:

```java
package com.example.orders.metrics;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class OrderEventMetricsTest {

    private final SimpleMeterRegistry registry = new SimpleMeterRegistry();
    private final OrderEventMetrics metrics = new OrderEventMetrics(registry);

    @Test
    void incrementsProcessedCounter() {
        metrics.markProcessed();
        metrics.markProcessed();

        assertThat(registry.get("orders.kafka.processed")
                .counter().count()).isEqualTo(2.0);
    }
}
```

For Spring Kafka integration tests, verify that template/listener observations or timers are registered when sending/receiving records. Use a real `MeterRegistry` in the test context and wait for listener processing to finish before asserting.

Things to verify:

1. Sending records successfully increments send/processed metrics as expected.
2. Producer failures or listener exceptions produce the appropriate result/error metrics.
3. Timers record non-zero counts and total time after operations.
4. Tags contain only values with controlled cardinality.
5. Consumer metrics are unbound when the factory closes clients if using factory listeners.
6. The Prometheus endpoint exports expected metric names and labels.
7. Observation/tracing does not create spans missing context or containing sensitive tags.

Do not assert exact millisecond durations in tests; verify only that the timer was recorded and has an expected count.

## 20. Implementation checklist

Before deploying Micrometer metrics for Kafka to production, verify:

1. Spring Boot, Spring Kafka, and Micrometer versions are compatible.
2. Actuator and the required registry/exporter are declared.
3. Metrics/Prometheus endpoints are exposed only within protected boundaries.
4. You decided between Micrometer timers and Observation based on version capabilities.
5. `KafkaTemplate` and listener containers are properly instrumented.
6. Native Kafka producer/consumer metrics are bound if client internals need monitoring.
7. Custom Counters/Timers/Gauges measure the right business boundaries.
8. Consumer lag has an appropriate measurement source at group/partition level.
9. Tags are low-cardinality; no event IDs or entity IDs are used.
10. Dashboards display throughput, latency, errors, lag, retry/DLT, and runtime.
11. Alerts distinguish sustained errors from brief traffic bursts.
12. Tests cover custom metrics and integration metrics.
13. Logs/traces exist to investigate individual events when metrics detect anomalies.

Micrometer helps Spring Kafka bring sending, receiving, and event processing into the application's unified metrics system. By combining Spring Kafka timers/observations, native Kafka client metrics, and business metrics, operations teams can monitor throughput, latency, errors, rebalances, and consumer lag. Keep tag cardinality low, choose instrumentation suited to your version, and combine metrics with logging/tracing to investigate both overall trends and individual events.

## 21. Self-check

1. Which different questions do metrics, logs, and traces answer when operating Kafka?
2. How do Spring Kafka operation metrics differ from native Kafka client metrics?
3. When should Observation be enabled for `KafkaTemplate` and listener containers?
4. What information do `KafkaClientMetrics` or Micrometer factory listeners collect?
5. When should you use Counter, Timer, Gauge, and DistributionSummary?
6. Why should `eventId` or `orderId` not be used as metric tags?
7. How does listener processing time differ from consumer lag?
8. Why should consumer lag be viewed per group and per partition?
9. How do you verify the exact metric names exported to Prometheus?
10. Why must metrics be combined with logs and traces when investigating a failing event?

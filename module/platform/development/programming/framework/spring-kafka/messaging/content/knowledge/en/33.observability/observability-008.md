# Measuring listener processing time

In a Spring Kafka application, listener processing time is the duration recorded by the container for a single listener invocation. Measuring this metric helps detect slow handlers, compare latencies across listeners, and monitor success/failure ratios. Spring Kafka integrates with Micrometer to create listener timers automatically; applications typically only need a `MeterRegistry` and appropriate tag configuration.

The listener timer answers the question **how long does each listener invocation take**. It is not end-to-end latency from when the producer sends a record until business processing finishes, nor does it replace consumer lag, Kafka fetch metrics, or retry/backoff wait times. To pinpoint why processing is slow, examine these signal groups together.

## 1. How does the listener timer work?

Since Spring Kafka 2.3, the listener container automatically creates and updates a Micrometer `Timer` whenever Micrometer is on the classpath and a suitable `MeterRegistry` is present in the application context. Timers are recorded for both successful and failed listener invocations.

The default meter name is `spring.kafka.listener`. Main tags:

| Tag | Value | Meaning |
|---|---|---|
| `name` | Listener container bean name | Identifies the measured listener/container |
| `result` | `success` or `failure` | Outcome of the listener invocation |
| `exception` | `none` or `ListenerExecutionFailedException` | Distinguishes successful calls from failed calls |

Example of an order-processing listener:

```java
@KafkaListener(id = "ordersListener", topics = "orders")
public void consume(OrderCreated event) {
    orderService.createOrder(event);
}
```

When the container calls `consume()`, the timer records the invocation duration. If the method returns normally, the sample falls under `result=success`. If the listener throws an exception to the container, the sample falls under `result=failure`.

The timer reflects the listener invocation duration measured by the container. If the listener performs synchronous database or REST calls, waiting on those calls is included in the processing time. If the listener merely launches an asynchronous task and returns immediately, the invocation timer may stop before the background work finishes. When you need to measure asynchronous business completion time, measure inside the async task itself or wrap the full lifecycle with an observation/span.

## 2. Requirements for Spring Kafka to create the timer automatically

To get automatic listener timers, the application needs:

1. Micrometer on the classpath.
2. A `MeterRegistry` in the Spring application context.
3. The listener executed by a Spring Kafka listener container.
4. `ContainerProperties.micrometerEnabled` not disabled.

`micrometerEnabled` defaults to `true`. In manual configuration, you can enable it explicitly:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated> orderListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setMicrometerEnabled(true);
    return factory;
}
```

When using Spring Boot Actuator with a compatible Micrometer registry, Boot usually auto-configures the registry and required components. If an application has multiple `MeterRegistry` beans, check how the registry is selected and how observation/metrics are configured; Spring Kafka documentation describes automatic timer creation when a single suitable registry exists in the context.

You can disable the listener timer if the application already uses a custom measurement mechanism:

```java
factory.getContainerProperties().setMicrometerEnabled(false);
```

Do not disable timers just to reduce metrics before understanding which meters are currently exported. Inspect the registry and observability setup first to avoid creating monitoring blind spots.

## 3. What data does a Timer measure?

A Micrometer `Timer` records the count of measured events and their total duration. Depending on configuration, the registry or backend can also provide max, histograms, or percentiles.

| Data | Interpretation |
|---|---|
| `count` | Number of listener invocations in the corresponding tag group |
| `total time` | Total duration of recorded invocations |
| `mean` | Mean duration, typically derived from total time / count |
| `max` | Maximum duration in the statistical window supported by the registry |
| `p95`, `p99` | Latency percentiles, requiring percentile or histogram configuration compatible with the registry/backend |

For example: over 5 minutes, a listener has 10,000 invocations with a total processing time of 50 seconds. The mean is roughly 5 ms. However, a low mean does not prove there are no slow records: if a few invocations take several seconds, `p95`/`p99` and `max` reveal the latency tail.

When exported to Prometheus, meter names and units may be normalized according to registry rules; for instance, a timer is represented as `_count`, `_sum`, and `_bucket` series if histograms are enabled. Do not assume `p95`/`p99` are automatically available just because a meter is a `Timer`; configure distribution statistics and verify real backend data.

## 4. Separating success and failure durations

Spring Kafka maintains separate timers via the `result` tag. You can use them to answer two distinct questions:

- Are successful invocations getting faster or slower?
- Are failures increasing or taking longer to fail?

For instance, a listener may fail quickly on validation errors, yet fail slowly when timing out on an external call. Both cases produce `result=failure`, so combine timers with logs, exceptions, and traces to find the exact cause.

The default `exception` tag on the listener timer uses `none` or `ListenerExecutionFailedException`. This is the wrapper exception used by the container when reporting listener errors; do not assume this tag always holds the root business exception class name. To see the root error, inspect stack traces, logs with correlation IDs, or trace spans.

## 5. Adding static tags to a listener

`ContainerProperties.setMicrometerTags()` lets you attach static tags to the listener timer. Example attaching service name and business domain:

```java
factory.getContainerProperties().setMicrometerTags(Map.of(
        "service", "order-service",
        "domain", "order",
        "environment", "production"
));
```

Static tags are useful when dashboards filter by service, environment, or listener group. Tag values should be bounded and stable. Never add order ID, user ID, email, correlation ID, or random values to tags because every new value can create a new time series and drive rapid cardinality growth.

## 6. Adding dynamic tags based on ConsumerRecord

Since Spring Kafka 2.9.8 and 3.0.6, `micrometerTagsProvider` allows generating tags from the record being processed. The provider receives `ConsumerRecord<?, ?>`; returned tags are merged with configured static tags.

```java
factory.getContainerProperties().setMicrometerTagsProvider(record -> {
    Header eventType = record.headers().lastHeader("event-type");
    String type = eventType == null
            ? "unknown"
            : new String(eventType.value(), StandardCharsets.UTF_8);

    return Map.of(
            "topic", record.topic(),
            "event_type", type
    );
});
```

Use dynamic tags only when the value set is small, such as known topics or a fixed set of event types. Never use keys, offsets, order IDs, or unbounded tenant IDs directly as tags. If you need to trace an individual record, record its ID in logs or traces instead of metric tags.

`micrometerTagsProvider` applies to record listeners; this provider is ignored for batch listeners. If a listener receives `List<ConsumerRecord<...>>`, choose static tags or design dedicated batch-level metrics/observations.

## 7. How does listener concurrency affect tags?

When using `ConcurrentMessageListenerContainer`, Spring Kafka creates a timer for each child container/thread. The `name` tag gets a `-n` suffix, where `n` runs from `0` to `concurrency - 1`.

For example, `concurrency = 3` can produce meter groups such as:

```text
spring.kafka.listener{name="ordersListener-0", result="success", ...}
spring.kafka.listener{name="ordersListener-1", result="success", ...}
spring.kafka.listener{name="ordersListener-2", result="success", ...}
```

This helps detect if one consumer thread has noticeably different processing times compared to the others. When viewing the whole listener, dashboards should aggregate series across common tag groups and strip the thread suffix when comparing at the service level.

Increasing concurrency does not automatically make each individual record process faster. It increases the number of consumer threads processing in parallel when the topic has enough partitions and resources. If one partition accumulates slow records or an external dependency called by the listener bottlenecks, per-thread timers help expose the imbalance.

## 8. Using Micrometer Observation instead of basic listener timers

Since Spring Kafka 3.0, you can enable Micrometer Observation for listener containers:

```java
factory.getContainerProperties().setObservationEnabled(true);
```

When Observation is enabled, basic Micrometer timers are disabled; timer metrics and traces are managed through observation. This is the right choice when you want to combine processing duration with distributed tracing and message context.

The default listener observation uses the `listener.id` tag. You can customize tags with `KafkaListenerObservationConvention` configured on container properties. Since Spring Kafka 3.0.6, the observation context includes `ConsumerRecord`, allowing dynamic attributes from the record. Keep cardinality bounded: metric tags must have a small value set; per-record IDs belong in traces or logs.

For batch listeners, per-record observations are not created by default because an observation is tied to a thread while a single listener invocation may contain many records. If you need per-record observation in a batch, enable:

```java
factory.getContainerProperties().setRecordObservationsInBatch(true);
```

When this property is enabled, Spring Kafka creates an observation for each record in the batch; those observations are not passed into the listener method. This enables per-record observability while keeping batch delivery in the listener. Without per-record batch observations enabled, batch listeners continue using the basic Micrometer timer for each batch invocation.

## 9. Distinguishing listener timers from Kafka client metrics

Listener timers and Kafka client metrics measure two different parts of the system:

| Metric group | What does it measure? | Used to diagnose |
|---|---|---|
| `spring.kafka.listener` | Listener invocation duration and processing outcome | Slow handlers, exceptions, differences across listener threads |
| Kafka consumer metrics | Poll, fetch, record rate, lag, and consumer state | Slow broker/network, consumer not keeping up with write rate |
| `spring.kafka.template` | Duration of sending records via `KafkaTemplate` | Slow producer sends or send failures |
| Application/database metrics | Duration of individual dependencies | Slow database queries, REST calls, or internal logic |

Spring Kafka can bind Kafka client metrics using `MicrometerConsumerListener` and `MicrometerProducerListener` on factories. Since Spring Kafka 3.3, `KafkaMetricsSupport` provides mechanisms to manage binding/unbinding `KafkaMetrics` for Kafka clients. These metrics complement the listener timer rather than replacing it.

For example, a rising listener timer with low consumer lag may point to slow business logic or dependencies inside the listener. Conversely, a stable listener timer with rising lag can indicate incoming record volume exceeds capacity, too few partitions, or consumer fetch/assignment issues.

## 10. Measuring an individual stage inside a listener

The automatic timer reports total listener invocation time measured by the container. To pinpoint which stage takes the most time, you can measure a specific block with Micrometer `Timer.Sample`.

Example measuring database save duration inside a listener:

```java
@Component
class OrderListener {

    private final MeterRegistry registry;
    private final OrderRepository repository;

    OrderListener(MeterRegistry registry, OrderRepository repository) {
        this.registry = registry;
        this.repository = repository;
    }

    @KafkaListener(topics = "orders", groupId = "order-service")
    void consume(OrderCreated event) {
        Timer.Sample sample = Timer.start(this.registry);
        try {
            this.repository.save(Order.from(event));
        }
        finally {
            sample.stop(Timer.builder("app.kafka.listener.database")
                    .description("Time spent saving an order from a Kafka listener")
                    .tag("listener", "orders")
                    .register(this.registry));
        }
    }
}
```

The `app.kafka.listener.database` timer measures repository save time specifically. Spring Kafka's `spring.kafka.listener` timer still measures the overall listener invocation. Comparing the two timers helps estimate how much time remains in mapping, validation, or other business steps.

Do not create a new timer per record or per ID. Register timers with stable tags and reuse meters managed by the registry.

## 11. Reading numbers and finding root causes of slowness

When a listener is slow, inspect signals in order:

1. **p95/p99 and max:** determine whether only a few records are slow or most records are slow.
2. **success/failure:** check whether failure rates rise alongside processing duration.
3. **per container/thread:** see if a single child container is slow due to a specific partition or skewed data.
4. **consumer lag and record rate:** check whether processing rate keeps up with write rate.
5. **dependency timers:** compare database/HTTP durations against the overall listener timer.
6. **retries and backoff:** distinguish listener execution time from time records spend waiting for retry. Backoff increases record age, but does not mean the listener method itself is running slowly.
7. **traces and logs:** locate specific records via correlation ID or trace ID; do not put those IDs into metric tags.

A baseline dashboard should include:

- Listener duration p50/p95/p99 and max.
- Invocation counts split by `result=success` and `result=failure`.
- Consumer lag by topic/partition/group.
- Records consumed rate and fetch latency.
- `KafkaTemplate` send duration.
- Retry, DLT, and external dependency error rates.

## 12. Key takeaways

- Spring Kafka creates listener `Timer`s automatically since 2.3 when Micrometer and a compatible `MeterRegistry` are present; `micrometerEnabled` defaults to `true`.
- The default meter is `spring.kafka.listener` with tags `name`, `result`, and `exception`.
- Concurrent containers create timers per child thread; the `name` tag gets suffixes `-0`, `-1`, ...
- Use `micrometerTags` for static tags and `micrometerTagsProvider` for tags derived from record listeners; avoid high-cardinality IDs.
- Enabling `observationEnabled` (since Spring Kafka 3.0) replaces basic timers with Micrometer Observation; batch listeners require per-record observation config if record-level visibility is desired.
- Listener timers measure listener invocation duration, not end-to-end latency or consumer lag.
- Combine listener timers, Kafka client metrics, dependency timers, retry metrics, and traces to locate the true bottleneck.

## References

- [Spring for Apache Kafka — Monitoring and Micrometer](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html)
- [Spring for Apache Kafka — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Spring for Apache Kafka — Micrometer Observation Documentation](https://docs.spring.io/spring-kafka/reference/appendix/micrometer.html)
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)

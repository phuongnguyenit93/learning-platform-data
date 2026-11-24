# Monitoring send and receive rates

In a Spring Kafka system, throughput shows how many records an application sends or processes per unit of time. Looking only at how many messages the producer sends is not enough: you must compare send rate, broker acknowledgment rate, consumer read rate, successful business processing rate, and backlog volume.

A useful dashboard answers three questions: how fast is the producer pushing data in, how fast is the consumer processing it, and is the gap between those two rates causing consumer lag to grow?

## 1. Distinguishing types of throughput

In an `orders` stream, you should monitor at least these quantities:

| Quantity | Meaning | Where measured |
| --- | --- | --- |
| Send attempt rate | Number of times the application invokes send per second | Before or at `KafkaTemplate.send()` |
| Send success rate | Number of sends acknowledged by the broker per second under producer settings | When the send future completes successfully |
| Consume rate | Number of records the consumer reads from Kafka per second | Kafka consumer client metrics |
| Processing success rate | Number of records processed successfully by business logic per second | Inside the listener/service |
| Processing failure rate | Number of processing failures per second | Error handler or listener |
| Byte throughput | Number of bytes sent/received per second | Producer/consumer client metrics |
| Consumer lag | Number of records a consumer group is behind the log end offset | Broker/exporter/monitoring |

These numbers are not necessarily equal. A producer may send successfully while the consumer processes slowly; a consumer may read fast while business processing fails; retries also cause a record to be delivered multiple times. When reporting business throughput, count records that completed successfully, not just how many times the listener was invoked.

## 2. Enabling Micrometer for Spring Kafka

Spring Kafka integrates with Micrometer to measure send duration via `KafkaTemplate` and listener container invocation duration. When Micrometer is on the classpath and the application context has a `MeterRegistry`, timers are created automatically:

- `spring.kafka.template`: duration of sending records via `KafkaTemplate`, split by success and failure outcomes.
- `spring.kafka.listener`: duration of listener invocations, split by success and failure outcomes.

Default timers include tags such as `name`, `result`, and `exception`. With a concurrent listener container, timers are created per consumer thread with corresponding suffixes on the container name. You can disable timers via `micrometerEnabled` on `KafkaTemplate` or `ContainerProperties` if your application has a specific reason.

To expose metrics via Spring Boot Actuator and Prometheus, add dependencies compatible with your Spring Boot version, typically Actuator and the Prometheus registry:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
```

Expose the required endpoints in application configuration:

```properties
management.endpoints.web.exposure.include=health,info,metrics,prometheus
```

Do not expose metrics endpoints to the public Internet. Configure authentication and network access restrictions according to operational policy.

## 3. Counting successfully sent records

`KafkaTemplate.send()` is an asynchronous operation. If you need to measure send success rate, increment the counter when the future completes successfully, not immediately when `send()` is called. The future completes according to the producer's acknowledgment mechanism and `acks` setting.

The example below uses the `CompletableFuture` API from Spring Kafka 3.x onward:

```java
@Service
public class OrderPublisher {
    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;
    private final MeterRegistry registry;
    private final Counter sendAttempt;
    private final Counter sendSuccess;
    private final Counter sendFailure;
    private final Timer sendCompletion;

    public OrderPublisher(
            KafkaTemplate<String, OrderEvent> kafkaTemplate,
            MeterRegistry registry) {
        this.kafkaTemplate = kafkaTemplate;
        this.registry = registry;
        this.sendAttempt = Counter.builder("orders.kafka.send")
            .tag("result", "attempt").register(registry);
        this.sendSuccess = Counter.builder("orders.kafka.send")
            .tag("result", "success").register(registry);
        this.sendFailure = Counter.builder("orders.kafka.send")
            .tag("result", "failure").register(registry);
        this.sendCompletion = Timer.builder("orders.kafka.send.completion")
            .register(registry);
    }

    public void publish(OrderEvent event) {
        sendAttempt.increment();
        Timer.Sample sample = Timer.start(registry);
        try {
            kafkaTemplate.send("orders", event.orderId(), event)
                .whenComplete((result, exception) -> {
                    sample.stop(sendCompletion);
                    if (exception == null) {
                        sendSuccess.increment();
                    } else {
                        sendFailure.increment();
                    }
                });
        } catch (RuntimeException ex) {
            sample.stop(sendCompletion);
            sendFailure.increment();
            throw ex;
        }
    }
}
```

This snippet illustrates measuring completion time and send outcomes. In Spring Kafka 2.x, `send()` returns `ListenableFuture`; callbacks must use that version's API. Do not block threads with `get()` just to update metrics in production flows.

The `orders.kafka.send.completion` timer measures the duration from calling send until the future completes. It includes send queuing and acknowledgment time, not consumer processing time. If you need to measure end-to-end business duration, add dedicated traces or business timestamps.

## 4. Measuring processing rate inside a listener

Count records where business processing completes successfully. If the listener throws an exception, increment the failure counter and rethrow so the Spring Kafka error handler can perform retries or recovery:

```java
@Component
public class OrderListener {
    private final OrderService orderService;
    private final MeterRegistry registry;
    private final Counter processed;
    private final Counter failed;
    private final Timer processingTime;

    public OrderListener(OrderService orderService, MeterRegistry registry) {
        this.orderService = orderService;
        this.registry = registry;
        this.processed = Counter.builder("orders.kafka.processed")
            .register(registry);
        this.failed = Counter.builder("orders.kafka.processing.failed")
            .register(registry);
        this.processingTime = Timer.builder("orders.kafka.processing")
            .publishPercentileHistogram()
            .register(registry);
    }

    @KafkaListener(topics = "orders", groupId = "order-projection")
    public void consume(OrderEvent event) {
        Timer.Sample sample = Timer.start(registry);
        try {
            orderService.apply(event);
            processed.increment();
        } catch (RuntimeException ex) {
            failed.increment();
            throw ex;
        } finally {
            sample.stop(processingTime);
        }
    }
}
```

In this example, `processed` increments only when `orderService.apply()` completes. `failed` counts listener failures, so the same event may increment this counter multiple times if retried. If you want to count unique events that ultimately fail, measure separately at the recoverer/DLT step.

## 5. Counting accurately when using batch listeners

With a batch listener, a single method invocation can process dozens or hundreds of records. Counting each method call measures batches per second, not records per second.

```java
private final Counter processedRecords; // Initialized via Counter.builder(...).register(registry)

@KafkaListener(
    topics = "orders",
    groupId = "order-batch-projection",
    containerFactory = "batchListenerFactory")
public void consume(List<OrderEvent> events) {
    orderService.applyBatch(events);
    processedRecords.increment(events.size());
}
```

Increment the counter only after the batch is processed successfully according to application semantics. If processing records individually inside a batch where one record can fail independently, count each record's outcome instead of blindly incrementing by the entire batch size. You can measure `batch.size` separately with a `DistributionSummary` to observe average batch size and distribution.

With Micrometer Observation, batch behavior depends on the Spring Kafka version. According to Spring Kafka 4.1 documentation, batch listeners do not create observations by default; you can enable `recordObservationsInBatch` on the container factory to create observations per record in a batch. Older versions differ in batch observation support, so check the documentation for your exact version before relying on this metric.

```java
factory.getContainerProperties().setRecordObservationsInBatch(true);
```

## 6. Collecting native metrics from the Kafka client

Spring Kafka timers measure listener invocations and template sends. To understand producers/consumers at the Kafka client layer, you can attach `MicrometerProducerListener` and `MicrometerConsumerListener` to the factories. These listeners manage `KafkaClientMetrics` when clients are created and closed:

```java
@Bean
public ConsumerFactory<String, OrderEvent> consumerFactory(
        MeterRegistry registry) {
    Map<String, Object> props = consumerProperties();
    DefaultKafkaConsumerFactory<String, OrderEvent> factory =
        new DefaultKafkaConsumerFactory<>(props);
    factory.addListener(new MicrometerConsumerListener<>(
        registry, Collections.singletonList(
            new ImmutableTag("service", "order-consumer"))));
    return factory;
}

@Bean
public ProducerFactory<String, OrderEvent> producerFactory(
        MeterRegistry registry) {
    Map<String, Object> props = producerProperties();
    DefaultKafkaProducerFactory<String, OrderEvent> factory =
        new DefaultKafkaProducerFactory<>(props);
    factory.addListener(new MicrometerProducerListener<>(
        registry, Collections.singletonList(
            new ImmutableTag("service", "order-producer"))));
    return factory;
}
```

Useful client metrics include:

| Group | Kafka client metric | Meaning |
| --- | --- | --- |
| Producer | `record-send-rate`, `record-send-total` | Records sent per second and total records sent. |
| Producer | `record-error-rate` | Send error rate. |
| Producer | `record-queue-time-avg` | Time records spend waiting in the producer queue before being sent. |
| Producer | `request-latency-avg` | Request latency to the broker. |
| Consumer | `records-consumed-rate`, `records-consumed-total` | Records read by the consumer per second and total read. |
| Consumer | `records-lag-max` | Maximum lag observed across partitions assigned to the consumer. |
| Consumer | `fetch-rate`, `fetch-latency-avg` | Frequency and latency of fetches from brokers. |

Metric names exported to Micrometer or Prometheus may be normalized differently from Kafka client JMX names. Inspect your environment's registry or metrics endpoint instead of assuming Prometheus names always match Kafka metric names.

## 7. Enabling Micrometer Observation and tracing

Since Spring Kafka 3.0, you can enable Micrometer Observation for `KafkaTemplate` and listener containers. Observation provides metrics and tracing by convention, linking send operations with receive operations when tracing is configured:

```java
kafkaTemplate.setObservationEnabled(true);
containerFactory.getContainerProperties()
    .setObservationEnabled(true);
```

When Observation is enabled, traditional Micrometer timers on the template/container are managed through observation rather than maintained in parallel. Therefore, do not add the numbers from both mechanisms together as if they were two separate sends or two separate processing runs.

You can customize tags via `KafkaTemplateObservationConvention` and `KafkaListenerObservationConvention`. Keep tags low-cardinality, such as listener ID, template name, topic, or consumer group. Avoid putting event ID, key, offset, customer ID, or exception message into metric tags.

## 8. Reading throughput alongside consumer lag

Throughput shows speed, while lag shows accumulating backlog. If a producer steadily sends 1,000 records/sec and a consumer steadily processes 1,000 records/sec, the backlog stays flat. If the producer continues at 1,000 records/sec while the consumer processes only 700 records/sec, the backlog grows by roughly 300 records/sec.

Kafka stores offsets per partition. Consumer lag is usually calculated as the difference between the log end offset and the consumer group's committed offset on a partition. Monitoring lag per partition helps detect a hot, slow partition even when overall throughput remains high.

Do not confuse a single consumer client's `records-lag-max` with the total consumer group lag across the cluster. A group lag dashboard from a broker/exporter or admin tool is generally suited for viewing the group's total backlog.

## 9. Diagnosing from metrics

| Symptom | Possibilities to check |
| --- | --- |
| Send attempts rise while send successes drop | Broker unavailable, serialization, timeouts, quotas, or producer errors. |
| `record-queue-time-avg` and request latency rise | Slow broker, batch/linger settings, network, or pressure on producer buffers. |
| Consumer read rate is high while processing success is low | Slow listener, business errors, heavy retries, or overloaded downstream. |
| Producer rate exceeds processing rate for a sustained period | Consumer lag grows; check concurrency, partition count, and processing time. |
| Only one partition has high lag | Key skew, a group of hot keys, or uneven processing across consumers. |
| Retry/DLT rises while throughput drops | Failing dependency or bad payloads consuming consumer time. |

When increasing concurrency, check the partition count and assignment distribution. A consumer group cannot use more active consumers than there are partitions; adding threads without adding partitions may not increase throughput.

## 10. Designing dashboards and alerts

An operational dashboard should include charts aligned on the same time window:

- Producer send success rate and send failure rate.
- Consumer records consumed rate and business processing success rate.
- Listener processing latency p50, p95, p99.
- Total consumer group lag and per-partition lag.
- Retry, recovery, and DLT rates.
- Producer buffer/queue time and consumer fetch latency.
- Queue depth, in-flight record count, and pause duration if backpressure is used.

Alert when lag increases continuously while processing rate stays below input rate, send failures cross a threshold, p95/p99 spikes abnormally, or the DLT rate jumps suddenly. Use multi-minute windows to avoid alerting on brief fluctuations.

## 11. Avoiding excessive metric cardinality

Metric tags should be dimensions with a bounded set of values useful for filtering dashboards. Suitable tags typically include `application`, `topic`, `group`, `listener`, `result`, and possibly `partition` if partition counts are controlled.

Do not use `eventId`, message key, offset, email, user ID, exception message, or payload as tags. Every new value can create a new time series; rapid series growth increases memory, CPU, and storage costs on the monitoring backend. To trace a specific event, use structured logs or distributed traces instead of metric tags.

## 12. Checklist for monitoring send and receive rates

- Distinguish send attempts, send successes, consume rate, and business processing successes.
- Enable Micrometer timers or Observation for templates and listeners according to your Spring Kafka version.
- Attach Kafka client metrics to producer/consumer factories when client-layer analysis is needed.
- For batch listeners, count the number of records in the batch instead of method invocation counts.
- Monitor consumer group lag and per-partition lag alongside throughput.
- Measure p95/p99 latency, retries, failures, and DLT alongside records/second.
- Keep metric tags low-cardinality; use logs/traces for individual events.
- Base alerts on trends and sustained duration rather than a single sample.

Effective send and receive rate monitoring combines `KafkaTemplate`, listener, Kafka client, and business metrics. When throughput is viewed alongside latency, error rates, and consumer lag, operations teams can pinpoint whether a bottleneck lies in the producer, broker, consumer, or downstream services, and tune partitions, concurrency, batching, or backpressure using data.

## References

- [Monitoring - Spring Kafka](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html)
- [Micrometer Observation Documentation - Spring Kafka](https://docs.spring.io/spring-kafka/reference/appendix/micrometer.html)
- [Spring Boot Actuator metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)

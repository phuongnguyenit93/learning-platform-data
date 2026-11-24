# Measuring Retry Attempts

## 1. Why Measure Retry Attempts?

In a Spring Kafka application, a record can be processed by a listener multiple times if an earlier attempt fails. Retries help overcome transient errors, yet without measurement, operations teams struggle to tell whether consumers are recovering cleanly or repeatedly hitting the same failure.

Measuring retry attempts helps answer key questions:

- How many processing attempts failed and how many redeliveries were triggered by the error handler?
- Which records are being retried repeatedly?
- Which exception groups generate most retries?
- How many records recovered successfully, and how many exhausted retries and went to the DLT?
- Are retries driving up consumer lag or overloading a dependency?
- Are retries happening inside the listener container or via retry topics?

Spring Kafka provides hooks to observe retries and delivery attempts. Applications can pair those hooks with Micrometer, logs, and tracing to build operational metrics.

## 2. Distinguishing Delivery Attempts from Retry Attempts

These two terms are often used interchangeably, but they are counted differently:

- **Delivery attempt** is the ordinal count of a listener receiving and attempting to process a record within a retry sequence tracked by the error handler.
- **Retry attempt** is the number of re-attempts after the initial delivery.

The initial delivery is already delivery attempt `1`, not a retry. Therefore:

\[
\text{Executed retry attempts} = \max(0,\text{Delivery attempt}-1)
\]

Example:

| Listener record reception | Delivery attempt | Retries before this attempt |
|---:|---:|---:|
| Initial delivery | 1 | 0 |
| First redelivery | 2 | 1 |
| Second redelivery | 3 | 2 |
| Third redelivery | 4 | 3 |

If `FixedBackOff(1_000L, 2L)` is configured, the listener can be invoked up to three times: once initially and twice as retries. The final delivery attempt is `3`; the maximum retry count is `2`.

When naming metrics, distinguish `delivery_attempt`, `failed_delivery_total`, and `retry_delivery_total`. Do not name a metric `retry_count` while counting the initial delivery in it.

## 3. Types of Retries to Separate When Measuring

A Spring Kafka system may contain multiple retry mechanisms with different scopes and counting semantics:

| Mechanism | Tracking component | Meaning |
|---|---|---|
| Blocking retry | `DefaultErrorHandler` / `RetryListener` | Redelivers the record inside the listener container's processing flow |
| Retry topic (non-blocking) | Spring Kafka Retry Topic headers | Record moves through retry topics and is handled by a retry consumer on a later delivery |
| Transaction rollback retry | `DefaultAfterRollbackProcessor` | Record is redelivered after a transactional listener rolls back |
| Producer send retry | Kafka producer metrics/configuration | Producer resends due to retriable broker/network errors; not a listener retry |
| Redelivery after restart/rebalance | Offsets, logs, and record identifiers | Record may be re-read because the offset was uncommitted; not necessarily an error handler retry |
| Retries inside business services | Service or retry-library metrics | E.g., a service calling a database or API multiple times within one listener invocation |

Do not lump all of these into a single metric if the goal is to measure `DefaultErrorHandler` effectiveness. Keep separate metrics for blocking retries, retry topics, transaction rollbacks, and producer send retries.

## 4. Tracking Retries with RetryListener

`RetryListener` is a Spring Kafka hook for receiving notifications when deliveries fail and when recovery concludes. One or more listeners can be registered on `DefaultErrorHandler`.

Primary callbacks:

| Callback | When invoked? | Information received |
|---|---|---|
| `failedDelivery(record, ex, deliveryAttempt)` | A listener attempt on the record fails | Record, exception, and the failed delivery attempt number |
| `recovered(record, ex)` | Recoverer successfully recovers the record after retries exhaust | Record and original exception |
| `recoveryFailed(record, original, failure)` | Recoverer throws an exception; recovery did not complete | Record, original processing error, and recovery error |

`RetryListener` has been supported since Spring Kafka 2.7. Overloads accepting `ConsumerRecords` for batch listeners were added in Spring Kafka 2.8.10. Check your dependency version before implementing batch callbacks.

### Registering a RetryListener

```java
@Bean
RetryListener orderRetryListener(MeterRegistry meterRegistry) {
    return new RetryListener() {

        @Override
        public void failedDelivery(
                ConsumerRecord<?, ?> record,
                Exception exception,
                int deliveryAttempt) {

            Counter.builder("app.kafka.listener.failed-delivery")
                    .tag("topic", record.topic())
                    .tag("exception", exception.getClass().getSimpleName())
                    .register(meterRegistry)
                    .increment();
        }

        @Override
        public void recovered(ConsumerRecord<?, ?> record, Exception exception) {
            Counter.builder("app.kafka.listener.recovered")
                    .tag("topic", record.topic())
                    .register(meterRegistry)
                    .increment();
        }

        @Override
        public void recoveryFailed(
                ConsumerRecord<?, ?> record,
                Exception original,
                Exception failure) {

            Counter.builder("app.kafka.listener.recovery-failed")
                    .tag("topic", record.topic())
                    .tag("exception", failure.getClass().getSimpleName())
                    .register(meterRegistry)
                    .increment();
        }
    };
}
```

Attaching the listener to the error handler:

```java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate,
        RetryListener orderRetryListener) {

    var recoverer = new DeadLetterPublishingRecoverer(dltTemplate);
    var handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L));

    handler.setRetryListeners(orderRetryListener);
    return handler;
}
```

`failedDelivery` is invoked for every failed attempt, including the initial delivery if that attempt fails. That is why the metric in the example is named `failed-delivery`, not `retry-delivery`. The callback provides `deliveryAttempt` to distinguish the initial attempt from redeliveries.

`recovered` measures records successfully recovered by the error handler; `recoveryFailed` measures cases where the recoverer failed. If you only count retries and ignore recovery, dashboards will not show whether records made it to the DLT or remained stuck in the stream.

## 5. Counting Retry Deliveries with `deliveryAttempt`

To count actual listener re-invocations, use the delivery attempt header. This header indicates the current delivery ordinal. When `deliveryAttempt > 1`, the record has been redelivered at least once within the error-handler-tracked retry chain.

Example listener recording retry deliveries:

```java
@Component
public class OrderListener {

    private final OrderService orderService;
    private final MeterRegistry meterRegistry;

    public OrderListener(
            OrderService orderService,
            MeterRegistry meterRegistry) {
        this.orderService = orderService;
        this.meterRegistry = meterRegistry;
    }

    @KafkaListener(
            topics = "orders",
            groupId = "order-service",
            containerFactory = "ordersListenerFactory")
    public void onOrder(
            OrderCreated event,
            @Header(KafkaHeaders.DELIVERY_ATTEMPT) int deliveryAttempt) {

        if (deliveryAttempt > 1) {
            Counter.builder("app.kafka.listener.retry-delivery")
                    .tag("topic", "orders")
                    .register(meterRegistry)
                    .increment();
        }

        orderService.process(event);
    }
}
```

This metric increments when the listener starts a redelivery, even if that redelivery succeeds. It measures observed retry deliveries, unlike the `failedDelivery` callback, which fires only when an attempt fails.

Do not add `deliveryAttempt` to a counter on every listener call. That value is the current ordinal, not the number of new retries generated in that call. Adding 2, 3, and 4 to a counter will inflate your numbers.

## 6. Enabling `KafkaHeaders.DELIVERY_ATTEMPT`

Since Spring Kafka 2.5, `DefaultErrorHandler` and `DefaultAfterRollbackProcessor` support the delivery attempt header for record listeners. This feature is disabled by default to avoid the minor overhead of tracking state and attaching a header to every record.

Enable it on container properties:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
ordersListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        DefaultErrorHandler orderErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(orderErrorHandler);
    factory.getContainerProperties().setDeliveryAttemptHeader(true);
    return factory;
}
```

The listener can read the header using `@Header`:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "ordersListenerFactory")
public void onOrder(
        OrderCreated event,
        @Header(KafkaHeaders.DELIVERY_ATTEMPT) int deliveryAttempt) {
    log.info("orderId={}, deliveryAttempt={}",
            event.orderId(), deliveryAttempt);
    orderService.process(event);
}
```

When using `DefaultKafkaHeaderMapper` or `SimpleKafkaHeaderMapper`, Spring can map the header to an `int` parameter. If consuming raw `ConsumerRecord`, the header value is a `byte[4]` that must be decoded:

```java
Header header = record.headers().lastHeader(KafkaHeaders.DELIVERY_ATTEMPT);
if (header != null) {
    int deliveryAttempt = ByteBuffer.wrap(header.value()).getInt();
}
```

This header applies to record listeners. Do not assume it is present in every batch listener or every redelivery following a restart or rebalance.

## 7. Delivery Attempt Headers with Batch Listeners

In a batch listener, records arrive as a batch, so tracking delivery attempts differs from record listeners. Since Spring Kafka 3.3, you can use `DeliveryAttemptAwareRetryListener` to attach the delivery attempt header to each `ConsumerRecord` in the batch:

```java
DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(new FixedBackOff(1_000L, 2L));

errorHandler.setRetryListeners(new DeliveryAttemptAwareRetryListener());

ConcurrentKafkaListenerContainerFactory<String, OrderCreated> factory =
        new ConcurrentKafkaListenerContainerFactory<>();
factory.setConsumerFactory(consumerFactory);
factory.setBatchListener(true);
factory.setCommonErrorHandler(errorHandler);
```

Inside the batch listener, read the header from each record:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "batchOrdersFactory")
public void onOrders(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (ConsumerRecord<String, OrderCreated> record : records) {
        Header header = record.headers()
                .lastHeader(KafkaHeaders.DELIVERY_ATTEMPT);

        int attempt = header == null
                ? 1
                : ByteBuffer.wrap(header.value()).getInt();

        log.info("partition={}, offset={}, deliveryAttempt={}",
                record.partition(), record.offset(), attempt);
        orderService.process(record.value());
    }
}
```

This capability requires Spring Kafka 3.3 or later. On older versions, use `RetryListener` batch callbacks if supported by your version, or track attempt counts at the application level using explicit record keys. Never read `KafkaHeaders.DELIVERY_ATTEMPT` from a batch assuming the header is always present.

## 8. Measuring Retry Topics (Non-Blocking Retry)

`@RetryableTopic` uses retry topics to defer re-attempts. Because this differs from `DefaultErrorHandler` blocking retries, do not rely on the blocking retry delivery attempt header as your sole metric.

You can read the non-blocking attempt count from `RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS`:

```java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 1_000, multiplier = 2.0))
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(
        OrderCreated event,
        @Header(
                name = RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS,
                required = false) Integer nonBlockingAttempts) {

    log.info("orderId={}, nonBlockingAttempts={}",
            event.orderId(), nonBlockingAttempts);
    orderService.process(event);
}
```

The retry topic header may be absent on the initial delivery, so the parameter should be nullable (`Integer`) with `required=false`. Do not use a primitive `int` for a header that may be missing.

The `attempts` attribute of `@RetryableTopic` is the total number of attempts before sending to the DLT, including the initial delivery. With `attempts = "4"`, there is normally one initial attempt and up to three retries. This differs from `FixedBackOff`, where `maxAttempts` counts retries after the initial delivery.

Since Spring Kafka 3.0.10, `KafkaMessageHeaderAccessor` offers a more convenient accessor:

```java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 1_000, multiplier = 2.0))
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(
        OrderCreated event,
        KafkaMessageHeaderAccessor accessor) {

    int blockingAttempts = accessor.getBlockingRetryDeliveryAttempt();
    int nonBlockingAttempts = accessor.getNonBlockingRetryDeliveryAttempt();

    log.info("orderId={}, blockingAttempts={}, nonBlockingAttempts={}",
            event.orderId(), blockingAttempts, nonBlockingAttempts);
    orderService.process(event);
}
```

The accessor returns `1` on the initial delivery for non-blocking retries. `getBlockingRetryDeliveryAttempt()` throws `IllegalStateException` if blocking delivery attempts have not been enabled. Only use this accessor on Spring Kafka 3.0.10 or later.

Both `@RetryableTopic` examples above use Spring Kafka 2.7 through 4.0 syntax: the `backoff` attribute with Spring Retry's `@Backoff` annotation. Starting in Spring Kafka 4.1, Spring Retry was removed as a dependency and the syntax changed to Spring Kafka's `backOff = @BackOff(...)`. Use the syntax matching the version declared in your project.

Do not mechanically add blocking attempts and non-blocking attempts together. They reflect two distinct retry layers; if an application combines both, dashboards should maintain separate metrics and clearly define total deliveries per layer.

## 9. RetryListener for Batches and Recovery

`RetryListener` provides overloads taking `ConsumerRecords<?, ?>` to monitor batch failures. Batch callbacks were added in Spring Kafka 2.8.10. Example:

```java
RetryListener retryListener = new RetryListener() {

    @Override
    public void failedDelivery(
            ConsumerRecords<?, ?> records,
            Exception exception,
            int deliveryAttempt) {

        log.warn("Batch delivery failed: records={}, attempt={}, cause={}",
                records.count(), deliveryAttempt,
                exception.getClass().getSimpleName());
    }

    @Override
    public void recovered(ConsumerRecords<?, ?> records, Exception exception) {
        log.info("Batch recovered: records={}", records.count());
    }

    @Override
    public void recoveryFailed(
            ConsumerRecords<?, ?> records,
            Exception original,
            Exception failure) {

        log.error("Batch recovery failed: records={}", records.count(), failure);
    }
};

errorHandler.setRetryListeners(retryListener);
```

Batch callbacks report failed batch processing attempts and do not always provide exact per-record retry counts. If per-record metrics are needed, read each record's delivery attempt header (Spring Kafka 3.3 with `DeliveryAttemptAwareRetryListener`) or track record identities and state appropriately yourself.

## 10. Designing Metrics with Micrometer

A minimal metric suite should distinguish failures, retry deliveries, successful recoveries, and failed recoveries:

| Recommended metric | Type | When incremented |
|---|---|---|
| `app.kafka.listener.failed-delivery` | Counter | Each `RetryListener.failedDelivery` callback |
| `app.kafka.listener.retry-delivery` | Counter | Each listener start with delivery attempt greater than 1 |
| `app.kafka.listener.recovered` | Counter | `RetryListener.recovered` callback |
| `app.kafka.listener.recovery-failed` | Counter | `RetryListener.recoveryFailed` callback |
| `app.kafka.retry-topic.delivery` | Counter | Each record received from a retry topic, per retry-topic header |
| `app.kafka.listener.processing` | Timer | Listener logic execution duration, measured via observation/interceptor or a timer around the service |

Appropriate dimensions typically include:

- `listener` or `group` with a bounded set of values.
- `topic` when topic count is controlled.
- `exception` using normalized class names.
- `result` such as `failed`, `recovered`, `recovery_failed`.
- `retry_type` such as `blocking`, `non_blocking`, `transactional`.

Never use `eventId`, `correlationId`, offset, key, or exception message as metric tags. These are high-cardinality values that can bloat metric system memory and storage costs. Put those values into logs or traces to investigate individual records.

With Spring Boot Actuator and Micrometer, counters registered on `MeterRegistry` can be exported via metrics endpoints or backends like Prometheus depending on application configuration. Name metrics consistently and inspect the actually exported metrics.

## 11. Record Identity for Correlating Logs and Metrics

To investigate a record retried multiple times, a stable identifier is required. You can use:

\[
\text{Record identity}=(\text{topic},\text{partition},\text{offset})
\]

In business systems, also include a unique `eventId` in the payload or headers. `topic-partition-offset` identifies the record within a Kafka log; `eventId` links the same event across different topics, such as the main topic, retry topics, and the DLT.

Structured logging example:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "ordersListenerFactory")
public void onOrder(
        OrderCreated event,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset,
        @Header(KafkaHeaders.DELIVERY_ATTEMPT) int deliveryAttempt) {

    log.warn("Kafka delivery: eventId={}, topic={}, partition={}, offset={}, attempt={}",
            event.eventId(), topic, partition, offset, deliveryAttempt);
    orderService.process(event);
}
```

When a record moves to a retry topic or DLT, its topic, partition, and offset can change. `eventId` connects processing attempts across topics. If the payload fails deserialization and `eventId` cannot be read, use the original topic, partition, offset, and timestamp for tracing.

## 12. Retry Count Is Not Consumer Lag

Consumer lag measures the offset distance between committed progress and the end offset. It is not the number of retries.

A consumer can have high lag simply because producers write faster than consumers read, even with zero retries. Conversely, a record might be retried many times while overall lag stays low if topic traffic is light.

| Metric | Question answered |
|---|---|
| Retry delivery count | How many times did the listener re-receive records due to tracked retries? |
| Failed delivery count | How many processing invocations failed? |
| Recovery count | How many records were recovered after retries exhausted? |
| DLT publish count | How many records were routed to the DLT? |
| Consumer lag | How far behind the end offset is the group? |
| Processing latency | How long does a single record processing attempt take? |
| Producer `record-retry-total` | How many times did the producer resend due to retriable send errors? |

For diagnosis, examine these metrics together. Rising lag alongside a rising retry rate points to a failing dependency; rising lag with a steady retry rate points to throughput limits, partition skew, or under-resourced consumers.

## 13. Redeliveries Not Counted as Error Handler Retries

The delivery attempt header and `RetryListener` track retries managed by the error handler. They are not global counters for every time Kafka redelivers a record.

For instance, the listener finishes updating the database, yet the process stops before committing the offset. After restart, the record can be redelivered from the older committed offset. Similarly, a rebalance can cause uncommitted records to be re-read by another consumer member. These are redeliveries caused by offset/commit semantics and do not necessarily pass through `DefaultErrorHandler`'s retry sequence.

If system-wide duplicate processing must be measured, also track processed `eventId` values or idempotency keys at the business layer. You cannot rely solely on `KafkaHeaders.DELIVERY_ATTEMPT` to detect all duplicates.

For transactional listeners, `DefaultAfterRollbackProcessor` also inherits retry listener support. You can register the same `RetryListener` on the processor to observe failed deliveries and recoveries after rollback; the delivery attempt header is likewise supported when enabled on the container. When aggregating dashboards, still tag `retry_type=transactional` to separate it from non-transactional `DefaultErrorHandler` metrics.

## 14. Pitfalls When Measuring Retry Attempts

| Mistake | Consequence | Right approach |
|---|---|---|
| Counting delivery attempt 1 as a retry | Retry count is inflated by one | Retry count equals delivery attempt minus 1 |
| Counting only `failedDelivery` callbacks | Misses successful retry deliveries | Count invocations with delivery attempt greater than 1 |
| Treating consumer lag as retry count | Misdiagnoses the cause of slowness | Track lag and retry metrics separately |
| Merging blocking and non-blocking retries | Cannot tell where records are retrying | Use separate metrics and distinguish corresponding headers |
| Assuming delivery headers work in batch mode on every version | Header missing or not updated as expected | Check version; from 3.3 use `DeliveryAttemptAwareRetryListener` for batches |
| Putting event ID or offset in metric tags | Cardinality explodes | Put record identity in logs/traces |
| Treating recovery callback as successful DLT publish for all custom recoverers | Metric misrepresents final action | Verify what the recoverer does and measure publish/durable-store results separately if needed |
| Ignoring recovery failures | Records may keep redelivering while dashboards report handled | Monitor `recoveryFailed` and DLT publish errors |

## 15. Testing Retry Metrics

Test scenarios should verify that metric definitions match actual runtime behavior:

1. **First-attempt success:** listener called with delivery attempt 1; retry delivery counter does not increment.
2. **Fail once then succeed:** listener called with attempts 1 and 2; retry delivery counter increments by 1; failed delivery callback records the first failure.
3. **Fail until BackOff exhausts:** verify invocation counts, `failedDelivery` callbacks, `recovered` callback, and DLT/recovery result.
4. **Recovery failure:** verify `recoveryFailed` increments and the record is not reported as recovered.
5. **Non-retryable exception:** verify zero retry deliveries while recovery is still recorded.
6. **Retry topic:** verify non-blocking header is absent on the initial delivery via raw header reads and populated on retry deliveries; test accessor if on a supported version.
7. **Batch listener:** verify batch callbacks and per-record delivery attempts match your Spring Kafka version.
8. **Restart before commit:** verify the record can be redelivered without necessarily incrementing blocking retry attempts as an error-handler retry.
9. **Metric cardinality:** confirm event IDs and offsets do not become tags.
10. **DLT:** confirm recovery metrics accurately reflect publish outcomes and records can be traced via `eventId`.

With `spring-kafka-test` or a Kafka test broker/container, verify callbacks, headers, offsets, and DLTs end to end. Use `CountDownLatch`, Awaitility, or timeout-bounded waits for async tests; avoid long unconditional `Thread.sleep()` calls.

## 16. Implementation Workflow for Measurement

1. Identify whether the application uses blocking retries, retry topics, transactional retries, or a combination.
2. Choose distinct metrics: failed delivery, retry delivery, recovered, recovery failed, and DLT publish.
3. For record listeners, enable `deliveryAttemptHeader` if reading attempt counts inside the listener.
4. Register `RetryListener` on `DefaultErrorHandler` to capture failure and recovery callbacks.
5. For retry topics, read `RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS` or use `KafkaMessageHeaderAccessor` from Spring Kafka 3.0.10+.
6. For batch listeners, check version support; use batch callbacks from 2.8.10+ and per-record delivery headers from 3.3+.
7. Export counters/timers to Micrometer with low-cardinality tags.
8. Log record identities into logs/traces for per-event investigation.
9. Correlate retry metrics with consumer lag, processing latency, DLT rate, and dependency health.
10. Test initial success, successful retry, exhausted retries, recovery failure, and restart/rebalance before deployment.

## 17. Summary

- Delivery attempts start at `1`; retry attempts are redeliveries after the initial attempt.
- `RetryListener` records failed deliveries, successful recoveries, and failed recoveries; batch callbacks were added in Spring Kafka 2.8.10.
- `KafkaHeaders.DELIVERY_ATTEMPT` is supported from 2.5 for record listeners and requires enabling `deliveryAttemptHeader` on container properties.
- For batch listeners, from Spring Kafka 3.3 onward, `DeliveryAttemptAwareRetryListener` attaches the header to each `ConsumerRecord`.
- Retry topics use `RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS`; the raw header may be absent on initial delivery, while `KafkaMessageHeaderAccessor` from 3.0.10 provides a normalized non-blocking attempt value.
- Measure failed delivery, retry delivery, recovered, recovery failed, and DLT publish separately.
- Consumer lag, producer send retries, and redeliveries after restart/rebalance are not equivalent to blocking retries.
- Put topic/partition/offset and event IDs in logs/traces; keep per-record identifiers out of metric tags.

By defining delivery attempts accurately and separating retry mechanisms, a Spring Kafka application can measure retry counts, recovery rates, and records needing investigation without confusing retries with consumer lag or offset-commit redeliveries.

## References

- [Spring Kafka Reference — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka Reference — Accessing Delivery Attempts](https://docs.spring.io/spring-kafka/reference/retrytopic/accessing-delivery-attempts.html)
- [Spring Kafka API — RetryListener](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/RetryListener.html)
- [Spring Kafka API — DeliveryAttemptAwareRetryListener](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/DeliveryAttemptAwareRetryListener.html)
- [Spring Kafka API — DefaultAfterRollbackProcessor](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/DefaultAfterRollbackProcessor.html)
- [Spring Kafka Reference — Retry Topic Features](https://docs.spring.io/spring-kafka/reference/retrytopic/features.html)
- [Spring Kafka Change History — Spring Kafka 4.1 retry API changes](https://docs.spring.io/spring-kafka/reference/appendix/change-history.html)
- [Apache Kafka Operations — Producer and Consumer Metrics](https://kafka.apache.org/40/operations/monitoring/)

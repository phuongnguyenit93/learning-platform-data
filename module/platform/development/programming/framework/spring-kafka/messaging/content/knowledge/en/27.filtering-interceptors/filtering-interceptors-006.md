# Interceptor Beans in Spring Kafka

An interceptor is a hook to observe or adjust records while a producer sends or a consumer receives data. Spring Kafka also provides interceptors at the listener container layer so the application can execute shared logic before and after the listener processes a record. As a result, tasks such as attaching trace context, recording metrics, or logging metadata can live in one place instead of being duplicated across every `@KafkaListener` method.

However, there are several kinds of interceptors at different layers. Spring Kafka's `RecordInterceptor` is not the same as the Kafka client's `ProducerInterceptor` or `ConsumerInterceptor`. Choosing the right layer helps avoid placing logic in the wrong lifecycle, missing callbacks, or accidentally altering offset commit behavior.

## 1. Where do interceptors sit in the Kafka flow?

On the consumer side, records pass through the Kafka client, the listener container, and then to the listener. Interceptors can be installed at two main layers:

- Kafka client `ConsumerInterceptor` receives `ConsumerRecords` after the client polls and before the Spring listener processes them.
- Spring Kafka `RecordInterceptor` or `BatchInterceptor` is invoked by the listener container around the listener invocation.

On the producer side, the Kafka client's `ProducerInterceptor` is invoked during `KafkaProducer.send()` and when the broker returns an acknowledgment. This interceptor is also used when the producer is created via `KafkaTemplate`, provided the interceptor configuration is passed to the producer factory.

```mermaid
flowchart TD
    A[Kafka topic] --> B[KafkaConsumer.poll]
    B --> C[ConsumerInterceptor.onConsume]
    C --> D[Spring Kafka listener container]
    D --> E[RecordInterceptor or BatchInterceptor]
    E --> F[@KafkaListener]
    F --> G[success / failure / afterRecord]
    H[KafkaTemplate.send] --> I[KafkaProducer.send]
    I --> J[ProducerInterceptor.onSend]
    J --> K[Kafka broker]
    K --> L[ProducerInterceptor.onAcknowledgement]
```

Interceptors fit shared technical logic. They do not replace listeners, deserializers, business validators, or error handlers. Those components have their own responsibilities and must be configured at the right layer.

## 2. Spring Kafka's `RecordInterceptor`

`RecordInterceptor<K, V>` lets the application intervene on each `ConsumerRecord` right before the listener is invoked. The interceptor receives the record and current consumer, then returns the record to proceed or returns `null` to skip the listener invocation for that record.

Example of an interceptor recording metadata and tracking processing outcomes:

```java
@Component
public class OrderRecordInterceptor
        implements RecordInterceptor<String, OrderEvent> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderRecordInterceptor.class);

    @Override
    public ConsumerRecord<String, OrderEvent> intercept(
            ConsumerRecord<String, OrderEvent> record,
            Consumer<String, OrderEvent> consumer) {

        log.debug("Receiving order event: topic={}, partition={}, offset={}, key={}",
                record.topic(), record.partition(), record.offset(), record.key());
        return record;
    }

    @Override
    public void success(
            ConsumerRecord<String, OrderEvent> record,
            Consumer<String, OrderEvent> consumer) {
        log.debug("Order event processed: eventId={}", record.value().eventId());
    }

    @Override
    public void failure(
            ConsumerRecord<String, OrderEvent> record,
            Exception exception,
            Consumer<String, OrderEvent> consumer) {

        log.warn("Order event failed: topic={}, partition={}, offset={}",
                record.topic(), record.partition(), record.offset(), exception);
    }
}
```

Attaching the interceptor to the listener container factory:

```java
@Configuration
public class OrderKafkaConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            orderListenerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory,
                    OrderRecordInterceptor interceptor) {

        ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
                new ConcurrentKafkaListenerContainerFactory<>();
        factory.setConsumerFactory(consumerFactory);
        factory.setRecordInterceptor(interceptor);
        return factory;
    }
}
```

Listener using this factory:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "orderListenerFactory")
public void consume(OrderEvent event) {
    orderService.process(event);
}
```

Declaring an interceptor with `@Component` only creates a Spring bean. The application still has to attach the bean to the factory via `setRecordInterceptor(...)` or an equivalent configuration mechanism; do not assume every bean of an interceptor type is automatically applied to all listener containers.

Commonly used callbacks:

| Callback | Timing | Purpose |
|---|---|---|
| `intercept(record, consumer)` | Before the listener processes the record | Read metadata, add technical context, or return an adjusted record. |
| `success(record, consumer)` | After the listener processes successfully | Record metrics or log success results. |
| `failure(record, exception, consumer)` | When listener processing throws an exception | Record the error and record context. |
| `afterRecord(record, consumer)` | After the listener invocation, regardless of success or failure | Clean up context or stop timing measurements. |

Default hooks and callback signatures may differ across Spring Kafka versions. When a project uses an older version, check the interface of the exact running version before implementing.

## 3. Using `BatchInterceptor` for batch listeners

If the listener receives entire `ConsumerRecords` or a list of records in a single poll, choose an interceptor designed for batches. `BatchInterceptor<K, V>` receives the entire batch and consumer rather than individual records.

Illustrative example:

```java
@Component
public class OrderBatchInterceptor
        implements BatchInterceptor<String, OrderEvent> {

    @Override
    public ConsumerRecords<String, OrderEvent> intercept(
            ConsumerRecords<String, OrderEvent> records,
            Consumer<String, OrderEvent> consumer) {

        log.debug("Received batch with {} records", records.count());
        return records;
    }

    @Override
    public void success(
            ConsumerRecords<String, OrderEvent> records,
            Consumer<String, OrderEvent> consumer) {
        log.debug("Batch processed: {} records", records.count());
    }

    @Override
    public void failure(
            ConsumerRecords<String, OrderEvent> records,
            Exception exception,
            Consumer<String, OrderEvent> consumer) {
        log.warn("Batch processing failed: count={}", records.count(), exception);
    }
}
```

Attach it to a factory configured for batch listeners:

```java
factory.setBatchListener(true);
factory.setBatchInterceptor(batchInterceptor);
```

Do not arbitrarily mix record and batch interceptors on the same listener factory. Match the listener type and interceptor: `RecordInterceptor` for record listeners, `BatchInterceptor` for batch listeners. This ensures callbacks receive the right processing unit and prevents misunderstanding one listener invocation as corresponding to a single record.

With batches, an exception may cause the whole batch or part of the batch to be retried depending on the error handler and how the listener reports the failing record position. Interceptors should record batch metadata; do not infer that all records succeeded merely because a batch callback ran.

## 4. Distinguishing interceptors from filtering

A common goal is skipping records that do not need processing. `RecordInterceptor` can return `null` to skip invoking the listener for that record, but if the primary goal is filtering on a simple business condition, `RecordFilterStrategy` expresses the intent more clearly.

Example processing only active orders:

```java
factory.setRecordFilterStrategy(record ->
        record.value() == null || record.value().isArchived());
```

With `RecordFilterStrategy`, returning `true` excludes the record from the listener; returning `false` keeps it for processing. When using manual acknowledgment and wanting discarded records acknowledged, you can configure `setAckDiscarded(true)` according to the container's ack policy.

| Mechanism | Skip condition | Meaning |
|---|---|---|
| `RecordInterceptor` | `intercept(...)` returns `null` | The listener is not invoked for that record. Useful when the skip decision needs interceptor context. |
| `RecordFilterStrategy` | `filter(record)` returns `true` | The record is excluded according to a separately declared filtering policy. |
| `BatchInterceptor` | Intervenes on a batch | Used for logic before/after a single batch listener invocation. |

Skipped records still require offset handling per the `AckMode` and container configuration. Do not assume that skipping the listener automatically acknowledges the record in every mode. Verify `RECORD`, `BATCH`, `MANUAL`, or `MANUAL_IMMEDIATE` behavior, especially when using `ackDiscarded`.

Filtering records also means that data does not pass through the listener's business logic. Only exclude records when skipping is intentional, explainable, and will not drop events that needed processing. If an invalid record needs investigation, use an error handler and DLT instead of filtering it out.

## 5. Kafka client `ProducerInterceptor`

`ProducerInterceptor<K, V>` belongs to the Kafka client and is invoked when the producer sends records and receives acknowledgments. It has two key callbacks:

- `onSend(record)` runs before the record is sent; it can return an adjusted record, such as adding a technical header.
- `onAcknowledgement(metadata, exception)` is invoked when the send outcome is determined, with metadata on success or an exception on failure.

Example:

```java
public class TraceProducerInterceptor
        implements ProducerInterceptor<String, OrderEvent> {

    @Override
    public ProducerRecord<String, OrderEvent> onSend(
            ProducerRecord<String, OrderEvent> record) {

        record.headers().add(new RecordHeader(
                "producer-service",
                "order-service".getBytes(StandardCharsets.UTF_8)));
        return record;
    }

    @Override
    public void onAcknowledgement(
            RecordMetadata metadata,
            Exception exception) {
        if (exception != null) {
            log.warn("Kafka send failed", exception);
        }
        else {
            log.debug("Kafka send acknowledged: topic={}, partition={}, offset={}",
                    metadata.topic(), metadata.partition(), metadata.offset());
        }
    }

    @Override
    public void close() {
    }

    @Override
    public void configure(Map<String, ?> configs) {
    }
}
```

Register the interceptor via producer properties:

```java
props.put(
        ProducerConfig.INTERCEPTOR_CLASSES_CONFIG,
        TraceProducerInterceptor.class.getName());
```

If using Spring Boot, you can pass Kafka client properties under `spring.kafka.producer.properties`:

```yaml
spring:
  kafka:
    producer:
      properties:
        "[interceptor.classes]": com.example.kafka.TraceProducerInterceptor
```

The Kafka client instantiates interceptors itself based on configuration; these are not Spring beans with automatic dependency injection. If the interceptor needs configuration, use `configure(Map<String, ?>)` or a dedicated factory mechanism. Avoid assuming Spring services can be directly injected into Kafka client interceptors.

`onSend` and `onAcknowledgement` may run on different threads. Interceptors must be thread-safe and not keep shared mutable state without proper synchronization. Per the Kafka client contract, exceptions thrown from interceptors are caught and logged by the client; do not use interceptors to replace send error handling in `KafkaTemplate` callbacks or producer listeners.

## 6. Kafka client `ConsumerInterceptor`

`ConsumerInterceptor<K, V>` belongs to the Kafka client and operates around the consumer's poll results. `onConsume(records)` receives `ConsumerRecords` before the Spring listener container forwards the data; `onCommit(offsets)` is invoked when the consumer commits offsets.

Example counting polled records:

```java
public class PollMetricsInterceptor
        implements ConsumerInterceptor<String, OrderEvent> {

    @Override
    public ConsumerRecords<String, OrderEvent> onConsume(
            ConsumerRecords<String, OrderEvent> records) {

        metrics.counter("kafka.consumer.polled.records").increment(records.count());
        return records;
    }

    @Override
    public void onCommit(
            Map<TopicPartition, OffsetAndMetadata> offsets) {
        log.debug("Consumer committed {} partition offsets", offsets.size());
    }

    @Override
    public void close() {
    }

    @Override
    public void configure(Map<String, ?> configs) {
    }
}
```

Register via consumer properties:

```java
consumerProps.put(
        ConsumerConfig.INTERCEPTOR_CLASSES_CONFIG,
        PollMetricsInterceptor.class.getName());
```

Or Spring Boot:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[interceptor.classes]": com.example.kafka.PollMetricsInterceptor
```

`ConsumerInterceptor` sees data at the Kafka client layer, before Spring listener container callbacks. It fits poll metrics or client-level commit observation. If you need hooks per listener success/failure invocation, `RecordInterceptor` is a better fit because its callbacks tie directly to the listener.

Do not call `poll()`, `commitSync()`, `commitAsync()`, `seek()`, or alter assignments from an interceptor. Those operations can corrupt the consumer lifecycle managed by the container. Use container APIs, acknowledgments, and error handlers to control offsets or retries.

## 7. Thread-safety and side effects

Interceptors are often configured on a factory shared by multiple listener containers or producers. When concurrency is greater than one, multiple consumer threads may call the same interceptor bean. Therefore, interceptors should be stateless or use thread-safe state.

Several guidelines:

1. Do not store the current record in a mutable field shared across threads.
2. Use Micrometer counters/timers or thread-safe loggers rather than building unsynchronized counters yourself.
3. Do not call databases, HTTP services, or slow I/O inside `intercept()`; doing so increases processing duration and raises consumer lag.
4. Do not execute business side effects inside interceptor callbacks. Records may be redelivered due to retries, rebalances, or restarts, causing side effects to run multiple times.
5. Do not commit offsets or control polling manually inside an interceptor of a container-managed consumer.
6. Do not alter the key, topic, or partition without understanding the impact on routing and ordering.
7. When adding headers, avoid overwriting correlation or tracing headers managed by other systems; standardize header names and encoding.

When using transactional listeners, interceptors are invoked in the container's processing flow, but side effects on external systems outside Kafka do not automatically roll back when a Kafka transaction aborts. Thus, interceptors should only record technical information or prepare metadata without business impact.

## 8. Choosing an interceptor by need

| Need | Mechanism to consider |
|---|---|
| Log/record metrics before and after each listener record | Spring Kafka `RecordInterceptor` |
| Log/record metrics for a single batch listener invocation | Spring Kafka `BatchInterceptor` |
| Exclude records based on a simple condition | `RecordFilterStrategy` |
| Add headers or observe send acknowledgments on the producer client | Kafka `ProducerInterceptor` |
| Observe poll results or commits on the consumer client | Kafka `ConsumerInterceptor` |
| Retry, recover, or route to DLT on listener errors | Spring Kafka error handler |
| Validate business data and reject commands | Validator or logic in service/listener |

Do not use interceptors to cram all shared logic into one place. If business processing is needed, invoke a business service from the listener so control flow and errors remain clear. If filtering is needed, use a filter strategy. If retries are needed, let exceptions propagate to the error handler.

## 9. Testing interceptors

Test both callbacks and the interceptor's impact on the listener/container:

- When `intercept()` returns a record, the listener receives the exact record and processes normally.
- When `intercept()` returns `null`, the listener is not invoked and offsets are handled according to the configured `AckMode`.
- When the listener succeeds, the `success` callback is called; when the listener throws an exception, the `failure` callback receives the corresponding exception.
- With batch listeners, the interceptor receives the expected batch and callbacks reflect the outcome of the batch invocation.
- `RecordFilterStrategy` returning `true` excludes records; verify `ackDiscarded` under the active acknowledgment mode.
- `ProducerInterceptor` adds headers properly and observes both successful and failed acknowledgments.
- `ConsumerInterceptor` receives the right polled record counts and commit callbacks do not alter offsets.
- When concurrency increases, the interceptor has no race conditions or improper state sharing across threads.
- When retries/rebalances occur, metrics and logs do not assume the interceptor runs only once per event.

In integration tests, you can use Embedded Kafka or a test broker to send real records through the listener container. For simple callbacks, unit tests can construct sample `ConsumerRecord` instances and invoke the interceptor directly. Either way, verify offset and retry behavior at the container when an interceptor filters records; merely checking the function's return value is not enough to prove the consumer flow operates correctly.

Interceptor beans help centralize technical logic around Kafka send/receive flows. Choose `RecordInterceptor` or `BatchInterceptor` when hooking into Spring Kafka listeners, `RecordFilterStrategy` when filtering records, and Kafka client interceptors when observing at the producer/consumer layer. Keep interceptors lightweight, thread-safe, and free of business side effects so the messaging pipeline remains understandable, retryable, and reliable to operate.

# Consumer Interceptor

A consumer interceptor is a component that runs on the path of a record from Kafka to the listener, allowing you to observe, enrich metadata, or apply common logic before/after listener processing. In Spring Kafka, the API commonly used for record listeners is `RecordInterceptor`; for batch listeners, there is `BatchInterceptor`. The Kafka client also has its own interface named `ConsumerInterceptor`, configured at the Kafka consumer level. These three APIs have different positions and lifecycles, so you must pick the right one for your goal.

In the `SPRING_KAFKA_MESSAGING` module, consumers receive events using `@KafkaListener`. Interceptors can support logging, tracing, metadata inspection, or measuring processing duration across multiple listeners. If the goal is to exclude records based on a condition, Spring Kafka has a dedicated `RecordFilterStrategy`; you should not turn an interceptor into the place holding all business logic.

## 1. Where does an interceptor sit in the consumer flow?

For a Spring Kafka record listener, the high-level flow:

```mermaid
flowchart LR
    A[Kafka broker] --> B[KafkaConsumer.poll]
    B --> C[Spring RecordInterceptor]
    C -->|record kept| D[@KafkaListener]
    C -->|returns null| E[Listener skipped]
    D --> F[Success / failure callback]
    F --> G[Container commits per AckMode]
```

`RecordInterceptor` is invoked after the consumer polls records and before the listener method processes them. It can return the record for the listener to proceed, or return `null` to skip that listener invocation. Lifecycle callbacks allow observing the processing outcome.

At the Kafka client level, `ConsumerInterceptor` is invoked by the Kafka consumer during `poll()` and when committing offsets. Spring `RecordInterceptor` sits at the listener container layer, making it a better fit when integrating with a Spring application and the listener lifecycle.

## 2. Distinguishing the three commonly confused APIs

| API | Package | Unit of processing | Primary purpose |
|---|---|---|---|
| `RecordInterceptor<K,V>` | `org.springframework.kafka.listener` | One `ConsumerRecord` | Intercept before/after each record listener invocation |
| `BatchInterceptor<K,V>` | `org.springframework.kafka.listener` | One `ConsumerRecords` from poll | Intercept a batch before/after a batch listener |
| `ConsumerInterceptor<K,V>` | `org.apache.kafka.clients.consumer` | `ConsumerRecords` and offset commits | Hook at the Kafka client level, independent of Spring's listener container |

If the application uses `@KafkaListener` and wants to use Spring beans, dependency injection, or listener success/failure callbacks, prefer `RecordInterceptor`/`BatchInterceptor`. Choose Kafka native `ConsumerInterceptor` when you need a hook at the Kafka client level, such as observing newly polled records or offset commits for every consumer configured with that interceptor.

## 3. Creating a `RecordInterceptor`

Example event used in this lesson:

```java
import java.math.BigDecimal;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        BigDecimal total,
        boolean active
) {}

public interface OrderApplicationService {
    void handle(OrderCreatedEvent event);
}
```

An interceptor can log metadata before the listener and log the outcome in callbacks:

```java
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.listener.RecordInterceptor;

public class OrderRecordInterceptor
        implements RecordInterceptor<String, OrderCreatedEvent> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderRecordInterceptor.class);

    @Override
    public ConsumerRecord<String, OrderCreatedEvent> intercept(
            ConsumerRecord<String, OrderCreatedEvent> record,
            Consumer<String, OrderCreatedEvent> consumer) {

        log.debug("Before listener: topic={} partition={} offset={}",
                record.topic(), record.partition(), record.offset());
        return record;
    }

    @Override
    public void success(
            ConsumerRecord<String, OrderCreatedEvent> record,
            Consumer<String, OrderCreatedEvent> consumer) {
        String eventId = record.value() == null
                ? "tombstone"
                : record.value().eventId();
        log.debug("Listener succeeded for eventId={}", eventId);
    }

    @Override
    public void failure(
            ConsumerRecord<String, OrderCreatedEvent> record,
            Exception exception,
            Consumer<String, OrderCreatedEvent> consumer) {
        log.warn("Listener failed for topic={} partition={} offset={}",
                record.topic(), record.partition(), record.offset(), exception);
    }

    @Override
    public void clearThreadState() {
        // Clear temporary ThreadLocal/context if the interceptor uses any.
    }

    @Override
    public void afterRecord(
            ConsumerRecord<String, OrderCreatedEvent> record,
            Consumer<String, OrderCreatedEvent> consumer) {
        log.trace("Listener invocation finished for offset={}", record.offset());
    }
}
```

`intercept()` is the decision point for which record is forwarded to the listener. `success()` and `failure()` allow observing the listener outcome; `afterRecord()` is a cleanup/post-processing callback after the listener invocation. These callbacks do not replace the error handler and do not decide retries or offset commits themselves.

If `record.value()` can be null, such as tombstones in a compacted topic, check for null before reading fields. Do not assume every record contains a non-null POJO.

## 4. Attaching the interceptor to the listener container factory

Spring Kafka lets you configure the interceptor on `ConcurrentKafkaListenerContainerFactory`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.RecordInterceptor;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public RecordInterceptor<String, OrderCreatedEvent> orderRecordInterceptor() {
        return new OrderRecordInterceptor();
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
            orderKafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderCreatedEvent> consumerFactory,
                    RecordInterceptor<String, OrderCreatedEvent> orderRecordInterceptor) {

        var factory = new ConcurrentKafkaListenerContainerFactory<
                String, OrderCreatedEvent>();
        factory.setConsumerFactory(consumerFactory);
        factory.setRecordInterceptor(orderRecordInterceptor);
        return factory;
    }
}
```

Listener selecting this factory:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    private final OrderApplicationService orderService;

    public OrderCreatedListener(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-projection",
            containerFactory = "orderKafkaListenerContainerFactory"
    )
    public void listen(OrderCreatedEvent event) {
        orderService.handle(event);
    }
}
```

A factory can be used by multiple listeners compatible with the same key/value types. If each listener needs a different policy, create separate factories or use an explicitly configured interceptor. When the application has multiple `RecordInterceptor` beans of the same type, use `@Qualifier` to inject the right interceptor.

## 5. Lifecycle callbacks

| Callback | When invoked? | Appropriate usage |
|---|---|---|
| `intercept(record, consumer)` | Before the listener processes the record | Inspect metadata, attach context, or return an adjusted record |
| `success(record, consumer)` | Listener processes successfully | Record metrics or log success results |
| `failure(record, consumer)` | Listener throws an exception | Record error metrics/logs, add diagnostic context |
| `afterRecord(record, consumer)` | After listener invocation | Clean up temporary context, stop timers, or close trace scopes |
| `clearThreadState()` | Container asks the interceptor to clear thread-bound state | Clean up `ThreadLocal` or state held per consumer thread |

The success/failure callbacks reflect the outcome of invoking the listener, not confirmation that the offset was successfully committed to the broker. Committing also depends on the container's `AckMode`, transactions, and error handling.

If the interceptor opens a tracing span or stores context in a `ThreadLocal`, it must close/clear that context on both success and failure paths. Do not leave data from the previous record around to be mistakenly reused by the next record on the same consumer thread.

## 6. Returning `null` and decisions to skip records

`RecordInterceptor.intercept()` can return `null`. When it does, the listener is not invoked for that record. This behavior affects data handling: the container may advance progress according to its acknowledgment mode, so the record may not be reprocessed as a normal failure.

Return `null` only when skipping is an intentional decision that can be explained and audited. For example, the record was already handled upstream and carries a clear marker indicating this consumer does not need to receive it. If a record is invalid or requires retry, throw an appropriate exception so the error handler handles it rather than returning null and losing the chance for recovery.

Do not use an interceptor for routine business filtering if Spring Kafka's `RecordFilterStrategy` serves better. A filter strategy clearly expresses the intent to discard records and has a dedicated `ackDiscarded` setting to decide whether discarded records are acknowledged.

## 7. Distinguishing interceptor and filter strategy

`RecordInterceptor` and `RecordFilterStrategy` have different goals:

| Criterion | `RecordInterceptor` | `RecordFilterStrategy` |
|---|---|---|
| Purpose | Observe/adjust records before the listener and provide post-processing callbacks | Decide whether a record is excluded from the listener |
| Primary API | `intercept()` returns a record or null | `filter()` returns a boolean |
| Lifecycle callbacks | Has success/failure/afterRecord | Not a listener success/failure hook |
| Used for | Logging, tracing, metadata, general checks | Skipping records based on a clear condition |
| Discard acknowledgment config | Not its primary responsibility | Has `ackDiscarded` to control acknowledgment of excluded records |

Example filter skipping inactive events:

```java
factory.setRecordFilterStrategy(record ->
        record.value() == null || !record.value().active());
factory.setAckDiscarded(true);
```

This snippet assumes the payload has an `active()` method and the factory uses a Spring Kafka version supporting `setAckDiscarded`. Choose `ackDiscarded` according to your acknowledgment mode and data policy: if discarding a record is a final decision, ensure offsets are handled as desired; otherwise, the record may be redelivered.

## 8. Using `BatchInterceptor` for batch listeners

If a listener receives multiple records per poll, you can use `BatchInterceptor`:

```java
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.springframework.kafka.listener.BatchInterceptor;

public class OrderBatchInterceptor
        implements BatchInterceptor<String, OrderCreatedEvent> {

    @Override
    public ConsumerRecords<String, OrderCreatedEvent> intercept(
            ConsumerRecords<String, OrderCreatedEvent> records,
            Consumer<String, OrderCreatedEvent> consumer) {

        return records;
    }

    @Override
    public void success(
            ConsumerRecords<String, OrderCreatedEvent> records,
            Consumer<String, OrderCreatedEvent> consumer) {
        // Record batch success metrics.
    }

    @Override
    public void failure(
            ConsumerRecords<String, OrderCreatedEvent> records,
            Exception exception,
            Consumer<String, OrderCreatedEvent> consumer) {
        // Record batch failure metrics.
    }

    @Override
    public void afterBatch(
            ConsumerRecords<String, OrderCreatedEvent> records,
            Consumer<String, OrderCreatedEvent> consumer) {
        // Clean up context after the batch listener completes.
    }
}
```

Attach the interceptor to a batch factory:

```java
factory.setBatchListener(true);
factory.setBatchInterceptor(orderBatchInterceptor);
```

A batch interceptor receives the poll's `ConsumerRecords` rather than individual `ConsumerRecord`s. Do not configure record and batch interceptors as if they share the same signature. If you need to drop individual records in a batch, consider a batch-capable filter strategy or process the list explicitly.

## 9. Kafka native `ConsumerInterceptor`

The Kafka client has the `org.apache.kafka.clients.consumer.ConsumerInterceptor<K,V>` interface. It is configured via the consumer's `interceptor.classes` property:

```java
import java.util.Map;

import org.apache.kafka.clients.consumer.ConsumerInterceptor;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;

public class ConsumerMetricsInterceptor
        implements ConsumerInterceptor<String, OrderCreatedEvent> {

    @Override
    public ConsumerRecords<String, OrderCreatedEvent> onConsume(
            ConsumerRecords<String, OrderCreatedEvent> records) {
        // Observe newly polled records; return records to the consumer.
        return records;
    }

    @Override
    public void onCommit(
            Map<TopicPartition, OffsetAndMetadata> offsets) {
        // Observe offsets committed by the consumer.
    }

    @Override
    public void configure(Map<String, ?> configs) {
    }

    @Override
    public void close() {
    }
}
```

Configure the class in `application.yml`:

```yaml
spring:
  kafka:
    consumer:
      properties:
        interceptor.classes: com.acme.kafka.ConsumerMetricsInterceptor
```

The Kafka client creates the interceptor according to its own configuration mechanism; do not assume this class is automatically managed by Spring as a bean with constructor injection. If you need Spring dependency injection, you should generally use `RecordInterceptor` or another Spring component at the listener layer.

`onConsume()` receives `ConsumerRecords` after poll and can return an adjusted set of records; `onCommit()` observes commit callbacks. Native interceptors do not replace `CommonErrorHandler`, do not open business transactions, and do not guarantee committed offsets under exactly-once semantics.

## 10. Interceptors with concurrency and thread safety

A listener container can run multiple consumer threads when concurrency is configured above one. Interceptors must be written assuming callbacks can run concurrently on different threads, especially if the same bean is attached to multiple containers.

- Prefer stateless interceptors.
- If temporary per-thread state is needed, use `ThreadLocal` and clean it up in `clearThreadState()`.
- Do not use a shared mutable `HashMap` to store record state without synchronization.
- Do not retain references to `ConsumerRecord` or payloads longer than the processing lifecycle unless necessary.
- Avoid network calls, database calls, or heavy work inside an interceptor because it sits on the consumer record-processing path.
- Do not call `poll()` or commit offsets manually from an interceptor; let the container and consumer manage the lifecycle.

Long-running interceptors reduce poll throughput and can cause the consumer to exceed `max.poll.interval.ms`, leading to leaving the group and triggering rebalances. Use interceptors for short, time-bounded, observable tasks.

## 11. Transactions, retry, and error handling

Interceptors do not replace transaction managers or error handlers. If a listener throws an exception, `failure()` can record the error, but retry/recovery decisions belong to the container:

- For normal listeners, a `CommonErrorHandler` such as `DefaultErrorHandler` handles retry/backoff/recovery.
- For transactional listener rollbacks, `AfterRollbackProcessor` coordinates seek/retry/recovery after rollback.
- For non-blocking retries, the retry topic topology is managed by `@RetryableTopic`.
- For filtered records, `ackDiscarded` and AckMode determine offset progress for excluded records.

Do not arbitrarily call `acknowledge()` or commit offsets from an interceptor. Doing so can break container semantics, especially with batch or transactional listeners.

## 12. Testing consumer interceptors

Interceptors should be tested at the unit level and integrated with the listener container:

- **Pass-through test:** `intercept()` returns the record properly and the listener receives the payload.
- **Null-return test:** interceptor returns null; verify the listener is not invoked and offset/discard behavior matches AckMode.
- **Success callback test:** listener succeeds; verify the `success()` callback is called.
- **Failure callback test:** listener throws an exception; verify `failure()` is called and the error handler still executes retry/recovery.
- **After-record cleanup test:** verify context/thread-local state is cleared after each record.
- **Batch test:** interceptor receives the expected `ConsumerRecords` and the batch listener processes the expected record set.
- **Native consumer test:** configure `interceptor.classes`, verify `onConsume()` and `onCommit()` are called.
- **Concurrency test:** run multiple consumer threads and verify there are no race conditions in interceptor state.

Use Embedded Kafka or Testcontainers for integration tests. For filter/null-return tests, check committed offsets and redelivery rather than only verifying the listener was not invoked.

## 13. Common mistakes

- **Confusing Kafka's `ConsumerInterceptor` with Spring's `RecordInterceptor`:** packages, configuration, and lifecycles differ.
- **Using an interceptor to run business processing:** makes listeners hard to test and mixes cross-cutting concerns with business logic.
- **Returning null on business errors:** the listener is skipped and the record may not go through retry/recovery as intended.
- **Using an interceptor instead of `RecordFilterStrategy`:** filtering intent and acknowledgment become harder to read.
- **Assuming `success()` means the offset is committed:** the listener callback and broker commit are two separate events.
- **Mutating shared state:** concurrency can cause race conditions or mix metadata across records.
- **Not cleaning up `ThreadLocal`:** context from a previous record leaks into the next record.
- **Calling network/database inside an interceptor:** slows down the consumer thread and increases rebalance risk.
- **Configuring a native interceptor and expecting Spring bean injection:** the Kafka client instantiates the class from config rather than using a Spring bean instance.
- **Committing/seeking from an interceptor:** can conflict with the listener container and AckMode.

## 14. Implementation checklist

- [ ] Selected the right API among `RecordInterceptor`, `BatchInterceptor`, or Kafka native `ConsumerInterceptor`.
- [ ] Interceptor only handles cross-cutting concerns such as logging, tracing, or metadata.
- [ ] `intercept()` returns valid records; only returns null when intentional skipping is defined.
- [ ] Business filtering uses `RecordFilterStrategy` with appropriate `ackDiscarded` configuration.
- [ ] Success/failure callbacks are not confused with offset commits.
- [ ] `ThreadLocal`/temporary state is cleaned up at the proper lifecycle points.
- [ ] Interceptor is thread-safe when the listener runs with concurrency.
- [ ] Consumer thread is not blocked by I/O or heavy work.
- [ ] Retries, DLT, and transactions remain managed by the container/error handling.
- [ ] Integration tests cover pass-through, null/filter, failure, batch, and concurrency.

Consumer interceptors are a useful extension point for applying consistent logging, tracing, and metadata along the event-receiving path. Choose `RecordInterceptor` for Spring record listeners, `BatchInterceptor` for batch listeners, or Kafka native `ConsumerInterceptor` for client-level hooks; keep interceptors short, thread-safe, and let filters, error handlers, and the container manage their respective responsibilities.

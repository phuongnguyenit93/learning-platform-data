# Avoiding Unexpected Payload Modifications

In Spring Kafka, interceptors can observe or intervene on a record before the listener processes it. Some interceptors even allow returning a new record or modifying the key, value, and headers. This capability is useful for tracing, auditing, or attaching metadata, but it also introduces risk: a seemingly small change can make the payload sent to Kafka differ from what the application created, or cause the listener to receive an unexpectedly altered object.

To keep payloads stable, you first need to properly distinguish the extension points: `ProducerInterceptor` runs on the producer side before serialization; Spring Kafka's `RecordInterceptor` runs before the listener; `ConsumerInterceptor` runs inside the Kafka consumer before `poll()` returns records; and `RecordFilterStrategy` excludes records from the listener. Each mechanism has different effects and responsibilities.

## 1. At what stages can a payload change?

A typical send/receive flow has the following steps:

```mermaid
flowchart LR
    A[Application creates event] --> B[ProducerInterceptor]
    B --> C[Serializer]
    C --> D[Kafka broker: bytes]
    D --> E[Deserializer]
    E --> F[ConsumerInterceptor]
    F --> G[Spring RecordInterceptor]
    G --> H[Message converter]
    H --> I[@KafkaListener]
```

Each step can change how data is seen:

- **Producer interceptor:** can alter the key/value or headers before the serializer converts objects into bytes. If the key/value is changed, the data actually written to Kafka changes as well.
- **Serializer:** determines how objects are encoded into bytes. This is the place for intentional wire-format conversion.
- **Consumer interceptor:** can modify or filter `ConsumerRecords` before the Kafka client returns them to the application.
- **Spring record interceptor:** runs before the listener; it can inspect, return a different record, or skip the listener by returning `null`.
- **Message converter:** converts deserialized data into a payload matching the listener signature. This is the place for intentional type conversion.
- **Listener/application service:** where business transformations happen. Domain changes should be explicitly written in this logic so they can be reviewed and tested.

An interceptor does not automatically guarantee payload immutability. The API contract allows some interceptor types to modify records; keeping data intact is the responsibility of the application's implementation and configuration.

## 2. Distinguishing the mechanisms

| Mechanism | Execution point | Can modify payload? | Suitable purpose |
|---|---|---|---|
| Kafka `ProducerInterceptor` | Before serialization and before the producer selects a partition if unspecified. | Yes; returns a new `ProducerRecord` or modifies headers/key/value. | Attaching producer metadata, tracing, send metrics. |
| Kafka `ConsumerInterceptor` | Before `KafkaConsumer.poll()` returns records to the application. | Yes; can transform or filter the record set. | Consumer observation at the Kafka client layer. |
| Spring `RecordInterceptor` | Inside the listener container, before invoking the record listener. | Yes; returns a different record or `null` to skip the listener. | Record observation, logging, attaching local context for processing. |
| Spring `BatchInterceptor` | Before invoking the batch listener. | Can inspect or return an adjusted batch per API. | Observing batch listeners. |
| Spring `RecordFilterStrategy` | In the adapter before the listener is invoked. | Not meant to modify payloads; decides whether the record is discarded. | Skipping duplicates or records that do not need processing. |
| Serializer/message converter | At the data conversion boundary. | Yes; this is their primary function. | Converting DTOs to bytes/JSON and back per contract. |

Do not use `RecordInterceptor` as a business filter when `RecordFilterStrategy` expresses the intent more accurately. Do not use an interceptor to silently turn an event into another event type; perform transformations in an application service or explicitly named mapper.

## 3. ProducerInterceptor can alter sent data

Kafka `ProducerInterceptor.onSend()` is called when the application calls `KafkaProducer.send()`, before the key/value are serialized. The interceptor can return a different `ProducerRecord`. Therefore, if you modify the key or value here, the serializer receives the modified data and the bytes stored in Kafka reflect that change.

Example of an interceptor that only adds a source-service header without touching key/value:

```java
import java.nio.charset.StandardCharsets;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerInterceptor;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.apache.kafka.common.header.internals.RecordHeader;

public class ProducerSourceInterceptor
        implements ProducerInterceptor<String, OrderEvent> {

    @Override
    public ProducerRecord<String, OrderEvent> onSend(
            ProducerRecord<String, OrderEvent> record) {

        record.headers().add(new RecordHeader(
                "producer-service",
                "order-api".getBytes(StandardCharsets.UTF_8)
        ));

        // Keep topic, partition, key, and value unchanged.
        return record;
    }

    @Override
    public void onAcknowledgement(RecordMetadata metadata, Exception exception) {
        // Only record concise metrics/logs; do not perform slow I/O.
    }

    @Override
    public void configure(Map<String, ?> configs) {
        // Read configuration if the interceptor needs it.
    }

    @Override
    public void close() {
        // Release dedicated resources if any.
    }
}
```

Register the interceptor via producer properties:

```yaml
spring:
  kafka:
    producer:
      properties:
        interceptor.classes: com.example.kafka.ProducerSourceInterceptor
```

In this example, a header is added to trace the sending service. The `OrderEvent` payload and key remain untouched. If the producer sends multiple value types, the interceptor's generic types must match the actual records; otherwise, type errors may only be logged by the Kafka interceptor without blocking the send.

### Why shouldn't you modify key/value in an interceptor?

Suppose the application creates an event:

```java
OrderEvent event = new OrderEvent("E100", "O100", 125_000);
kafkaTemplate.send("orders.events", event.orderId(), event);
```

If `onSend()` modifies `event.amount()` or replaces the key, Kafka receives a different payload from the object passed by the caller. This can break event signatures, partition routing, log compaction, or reconciliation between the application and Kafka.

If you need to normalize data before sending, create a new object in the application layer:

```java
OrderEvent normalized = orderEventMapper.normalize(event);
kafkaTemplate.send("orders.events", normalized.orderId(), normalized);
```

The method name `normalize` clearly indicates data transformation. You can unit-test the mapper and compare input/output objects without depending on the producer interceptor lifecycle.

### Notes on errors and multithreading

Kafka invokes producer interceptors from multiple threads. Implementations must be thread-safe if they hold shared state. Furthermore, exceptions thrown from `ProducerInterceptor` callbacks are caught and logged by Kafka rather than propagated back to the caller as a reliable validation mechanism. Therefore:

- Do not use `onSend()` to reject invalid payloads.
- Validate events before `KafkaTemplate.send()`.
- Do not hold a shared mutable `StringBuilder`, `HashMap`, or buffer without synchronization.
- Keep callbacks fast; `onAcknowledgement()` may run on the producer's I/O thread.
- Avoid building chains of interceptors that mutate payloads depending on one another's results.

## 4. ConsumerInterceptor can alter records before the application

Kafka `ConsumerInterceptor.onConsume()` is called before `KafkaConsumer.poll()` returns `ConsumerRecords` to the calling code. The API permits the interceptor to return a new record set, filter records, or fabricate records. Exceptions from callbacks are caught and logged by Kafka, not propagated to the caller.

The danger is that the consumer has already polled and updated its read position before the application processes the record set after the interceptor. If an interceptor silently drops a record, the application may never see that record while the consumer position still advances. Once the offset is committed, the record has been skipped at the application level.

Hence, do not use Kafka `ConsumerInterceptor` to drop business events or modify payloads. If you need to intentionally skip records in a Spring listener, use `RecordFilterStrategy` and clearly define the acknowledgment/commit policy. If you need to inspect data, return the original record set and only record metrics/logs.

Example configuring a consumer interceptor on the Kafka client:

```java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.consumer.ConsumerConfig;

Map<String, Object> consumerProperties = new HashMap<>();
consumerProperties.put(
        ConsumerConfig.INTERCEPTOR_CLASSES_CONFIG,
        ConsumerAuditInterceptor.class.getName()
);
```

With Spring Boot you can set `spring.kafka.consumer.properties.interceptor.classes`. Note that Kafka interceptors are instantiated and managed by the Kafka client; they do not automatically become Spring beans receiving constructor injection. If Spring dependencies are needed, configure them manually via `configure()` or consider Spring `RecordInterceptor`.

## 5. Spring RecordInterceptor: observing before the listener

`RecordInterceptor<K,V>` is invoked by Spring Kafka before the record listener processes the record. With the modern API, `intercept()` receives both `ConsumerRecord` and `Consumer`; it can return the original record, a different record, or `null` to skip the listener.

Example that only logs metadata without altering the payload:

```java
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.listener.RecordInterceptor;
import org.springframework.stereotype.Component;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Component
public class OrderAuditRecordInterceptor
        implements RecordInterceptor<String, OrderEvent> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderAuditRecordInterceptor.class);

    @Override
    public ConsumerRecord<String, OrderEvent> intercept(
            ConsumerRecord<String, OrderEvent> record,
            Consumer<String, OrderEvent> consumer) {

        log.debug("Receiving topic={}, partition={}, offset={}, key={}",
                record.topic(), record.partition(), record.offset(), record.key());

        // Return the exact same record; do not modify key, value, or headers.
        return record;
    }
}
```

Attach the interceptor to the listener container factory:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> orderListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        OrderAuditRecordInterceptor auditInterceptor) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setRecordInterceptor(auditInterceptor);
    return factory;
}
```

With `@KafkaListener`, choose the factory:

```java
@KafkaListener(
        topics = "orders.events",
        groupId = "order-projection",
        containerFactory = "orderListenerFactory"
)
public void listen(OrderEvent event) {
    orderService.apply(event);
}
```

### Mandatory rules when returning a different record

Spring Kafka allows `RecordInterceptor` to return a different `ConsumerRecord`. If you do so, **topic, partition, and offset must be preserved**. Changing these positioning fields can cause the container to process or commit the wrong offsets, leading to missed or duplicated records.

Beyond those three fields, when creating a new record, preserve timestamp, timestamp type, serialized key/value sizes, headers, and leader epoch when supported by the Kafka API version. Do not use a simplified constructor and accidentally drop metadata needed by the listener, tracing, or dead-letter recoverer.

Do not mutate the `record.value()` object in place. `ConsumerRecord` does not allow replacing the value reference after creation, yet the value object itself may be mutable. For instance, an `OrderEvent` with setters can still be modified:

```java
// Avoid: the object received by the listener has been mutated inside the interceptor.
record.value().setAmount(0);
return record;
```

If you truly need to create a normalized view, construct a new object explicitly and replace the payload only when the listener contract permits it. When the goal is preserving the payload intact, the safe option is returning the original input record.

## 6. Callbacks after the listener runs

Since Spring Kafka 2.7, `RecordInterceptor` includes `success()` and `failure()` callbacks; since 2.8, it includes `afterRecord()`. They help record processing outcomes without wrapping the entire listener method.

```java
@Override
public void success(ConsumerRecord<String, OrderEvent> record,
        Consumer<String, OrderEvent> consumer) {
    metrics.increment("orders.listener.success");
}

@Override
public void failure(ConsumerRecord<String, OrderEvent> record,
        Exception exception,
        Consumer<String, OrderEvent> consumer) {
    metrics.increment("orders.listener.failure");
}

@Override
public void afterRecord(ConsumerRecord<String, OrderEvent> record,
        Consumer<String, OrderEvent> consumer) {
    // Clean up per-thread state if the interceptor created temporary state.
}
```

These callbacks are appropriate for metrics and cleanup. Do not mutate the payload in `success()` or `failure()` expecting to alter data the listener already processed. If you need to pass information across callbacks, store only minimal per-thread metadata and clean it up in `afterRecord()`/`clearThreadState()`.

### Interceptors and transactions

By default, interceptors are invoked before the transaction starts (`interceptBeforeTx=true`). You can set `interceptBeforeTx=false` if the interceptor needs to run inside the container's transaction. When using transactions, if `intercept()` can throw an exception, it must not be combined with `interceptBeforeTx=true` per the current API contract; verify the transaction configuration and interceptor position before letting errors escape from an interceptor.

Do not call methods that alter consumer position or committed offsets from an interceptor. The listener container manages polling, seeking, acknowledgment, and commits; direct intervention can break processing semantics.

## 7. Use RecordFilterStrategy when the goal is excluding records

If the goal is not to invoke the listener for a specific record, use `RecordFilterStrategy`. Its `filter()` method returns `true` when the record should be discarded and `false` for the listener to keep receiving it. This mechanism expresses filtering intent more clearly than returning `null` from an interceptor.

Example skipping events marked as ignored:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.listener.adapter.RecordFilterStrategy;

@Bean
RecordFilterStrategy<String, OrderEvent> ignoredOrderFilter() {
    return record -> record.value().isIgnored();
}
```

Attach the filter to the factory:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.adapter.RecordFilterStrategy;

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> filteredOrderFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        RecordFilterStrategy<String, OrderEvent> ignoredOrderFilter) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setRecordFilterStrategy(ignoredOrderFilter);
    factory.setAckDiscarded(true);
    return factory;
}
```

Or since Spring Kafka 2.8.4, select a dedicated filter per listener using the `filter` attribute:

```java
@KafkaListener(
        id = "orderListener",
        topics = "orders.events",
        filter = "ignoredOrderFilter"
)
public void listen(OrderEvent event) {
    orderService.apply(event);
}
```

`ackDiscarded` defaults to `false`. When using manual acknowledgment, set `true` if discarded records must be acknowledged/committed per the application's policy. For other AckModes, understand how the container commits offsets and test that filtered records are neither re-read endlessly nor skipped unintentionally. Do not use filtering for transient errors that need retries; let exceptions go through the error handler.

For batch listeners, Spring Kafka provides `FilteringBatchMessageListenerAdapter`. When overriding `filterBatch()`, return the remaining list of records; to discard the whole batch, return an empty list rather than `null`. Since Spring Kafka 3.3, `ignoreEmptyBatch()` allows skipping the listener invocation when the post-filter batch is empty; if enabled, the container still performs commits according to configuration.

## 8. Producer/consumer interceptors are not for data validation

A common misconception is that Kafka client interceptor callbacks act as a validation gate that can reject records. Exceptions in `ProducerInterceptor` and `ConsumerInterceptor` are caught and logged by Kafka rather than propagated to the API caller as normal validation errors.

If a payload is invalid, validate it before sending:

```java
public void publish(OrderEvent event) {
    validator.validate(event); // Throws an exception if the payload is invalid.
    kafkaTemplate.send("orders.events", event.orderId(), event);
}
```

If received data is invalid, let the deserializer, message converter, or listener throw an appropriate exception so `DefaultErrorHandler`, retries, and DLT handle it per policy. Do not silently mutate payloads in an interceptor to mask producer or schema errors.

## 9. Mutable payloads and defensive copying

Kafka records pass through multiple layers within the same process. If the value is a mutable object, multiple components may hold the same reference. Modifying the object in an interceptor or helper can cause the listener to see altered data.

Options to avoid unexpected changes:

- Use immutable DTOs, such as Java `record`s, with immutable fields.
- Make fields `final` and omit setters.
- For collections, use unmodifiable copies (`List.copyOf`, `Map.copyOf`) when constructing events.
- If transformation is needed, create a new object rather than mutating the input object.
- Do not share mutable buffers, byte arrays, or collections across threads without defensive copies.
- Do not reuse an event object and mutate its fields after calling `KafkaTemplate.send()`; the serializer may run asynchronously after that call.

Example immutable DTO:

```java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        BigDecimal amount,
        Instant occurredAt
) {}
```

`record` prevents fields from being reassigned after construction. If a record contains a `byte[]`, `List`, or other mutable object, copy that data on input and output; Java records do not automatically make nested objects immutable.

## 10. Headers can also be modified

`ProducerRecord` and `ConsumerRecord` may expose mutable `Headers`. Adding or removing headers does not directly alter the payload value, yet it still changes metadata that downstream components may rely on.

For instance, an interceptor removing `event-type` can prevent the consumer from identifying the event type; removing `correlation-id` breaks tracing; overwriting `schema-version` can cause the deserializer to pick the wrong schema.

Principles to follow:

- Only add clearly namespaced headers, such as `x-producer-service` or `x-trace-id`.
- Do not overwrite business headers or framework-managed headers without a contract.
- When updating a value, clarify whether the header may repeat or must have a single value; Kafka permits multiple headers with the same name.
- Do not place tokens, credentials, or sensitive data into headers merely for logging convenience.
- Assert headers before and after interceptors in tests.

## 11. Thread safety and dependency injection

`ProducerInterceptor` can be invoked concurrently from multiple producer threads. `ConsumerInterceptor` is managed by Kafka alongside the consumer instance. Spring `RecordInterceptor` can be used by multiple child containers when listener concurrency is greater than one. Therefore, do not keep shared mutable state inside an interceptor without protection.

The Kafka client creates producer/consumer interceptors per the `interceptor.classes` setting; they are not Spring beans by default. If you need to inject Spring services, Spring Kafka documentation guides passing dependencies via `configure()` or customizing the factory. For logic specific to Spring listeners, `RecordInterceptor` is a more natural choice because it can be declared as a bean and receive dependencies via constructor injection.

Do not execute database queries or slow HTTP calls inside a producer interceptor. `onSend()` sits on the record send path and can increase latency; `onAcknowledgement()` may run on the I/O thread. For consumer interceptors, callbacks sit on the poll path. For Spring record interceptors, slow processing also lengthens the time the consumer thread is away from polling the broker.

## 12. Composite interceptors and execution order

Spring Kafka provides `CompositeRecordInterceptor` and `CompositeBatchInterceptor` to run multiple interceptors. The Kafka producer also allows registering multiple `ProducerInterceptor`s; they are invoked in configured order, with the next interceptor receiving the record returned by the previous one.

If multiple interceptors mutate payloads or headers, the outcome depends on execution order and the state left behind by earlier interceptors. This makes diagnosing why data changed much harder.

Organize the pipeline as follows:

1. Interceptors observe/log/collect metrics and return the original record unchanged.
2. If metadata must be added, each interceptor owns its own distinct set of headers.
3. Payload transformations occur in an explicitly named mapper/service, not split across hidden interceptors.
4. Include tests confirming callback ordering and final output when composites are used.

Since Spring Kafka 4.0, container factories and containers expose getters for record/batch interceptors; when using a composite, you can add interceptors to the composite after the container is created. For older versions, configure the full chain before creating the container.

## 13. Testing to prove payloads are not modified

Tests should verify data on both sides of an interceptor rather than only checking whether the listener was called.

### Unit test for ProducerInterceptor

- Construct a `ProducerRecord` with known key/value/headers.
- Call `onSend()`.
- Compare topic, partition, key, and value before and after.
- Verify only permitted added headers appear.
- Verify no business headers were deleted or overwritten.

### Unit test for Spring RecordInterceptor

- Pass a sample `ConsumerRecord` into `intercept()`.
- Verify the exact same record is returned if the interceptor only observes.
- If returning a new record, verify topic/partition/offset and required metadata are preserved.
- Verify the value object was not mutated.
- Verify `success`, `failure`, and `afterRecord` callbacks do not modify the payload.

### Integration test with Kafka

1. Send an event with specific `eventId`, key, value, and headers.
2. Consume the record via the target listener container factory.
3. Have the listener record the received payload and metadata.
4. Compare the payload received by the listener against the original payload.
5. Verify the filter only discards selected records and remaining records are processed properly.
6. Verify offsets/acknowledgments after filtering, especially with `MANUAL` or `MANUAL_IMMEDIATE`.
7. Run with concurrency greater than one if the interceptor holds any shared state.

Example assertion for an observation-only interceptor:

```java
ConsumerRecord<String, OrderEvent> before = createRecord(event);
ConsumerRecord<String, OrderEvent> after = interceptor.intercept(before, consumer);

assertThat(after).isSameAs(before);
assertThat(after.value()).isEqualTo(event);
assertThat(after.topic()).isEqualTo(before.topic());
assertThat(after.partition()).isEqualTo(before.partition());
assertThat(after.offset()).isEqualTo(before.offset());
```

If the event is a mutable object, add assertions on nested fields or use an immutable DTO for comparison. Do not compare references alone, because the same object instance could have been mutated in place.

## 14. Common mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| Consumer receives a different amount than the original object | Producer interceptor or mapper mutated a mutable value before serialization. | Check `onSend()`, construct a new DTO in the application layer, and test payloads before/after. |
| Listener receives an altered object | Spring `RecordInterceptor` mutated `record.value()` in place. | Use immutable DTOs and return the original record. |
| Records are lost or offsets handled incorrectly | Interceptor returned a new record with a different topic/partition/offset. | Preserve all three positioning fields; preferably do not replace the record unnecessarily. |
| Events skipped unexpectedly | `RecordInterceptor` returned `null` or `ConsumerInterceptor` filtered records. | Use `RecordFilterStrategy` with a clear acknowledgment policy. |
| Filtered records are re-read | `ackDiscarded`/AckMode mismatch with how the application manages acknowledgment. | Clarify commit semantics and test with a real group. |
| Validation error fails to block producer send | `ProducerInterceptor` threw an exception, which Kafka only logs. | Validate in the application service before `KafkaTemplate.send()`. |
| Trace headers disappear | Interceptor removed or overwrote framework/app-managed headers. | Namespace headers explicitly and assert headers after the pipeline. |
| Behavior changes under higher concurrency | Interceptor holds non-thread-safe mutable state. | Make interceptors stateless or use appropriate concurrent structures. |
| Spring dependency inside Kafka interceptor is null | Kafka client creates the interceptor without Spring bean lifecycle. | Wire via `configure()`/factory or use Spring `RecordInterceptor`. |
| Batch listener not filtered as expected | Wrong adapter used or listener receives raw `ConsumerRecords`. | Use the proper batch filter; note `ConsumerRecords` is immutable and batch adapters do not apply to that parameter type. |

## 15. Pre-production checklist for interceptors

- The interceptor has a clear purpose: observation, metadata enrichment, filtering, or data transformation.
- Key/value are not modified unless explicitly required and the data contract is versioned.
- When adding headers, only header names owned by the interceptor's scope are used.
- When returning a different record from `RecordInterceptor`, topic/partition/offset remain unchanged.
- Consumer seek/commit or position changes are never invoked from an interceptor.
- Exceptions in Kafka producer/consumer interceptors are not used as validation gates.
- Interceptor state is thread-safe and callbacks perform no slow I/O.
- Filtering uses `RecordFilterStrategy` with an explicit `ackDiscarded`/AckMode policy.
- Payload DTOs are immutable or defensively copy nested collections/arrays.
- Unit and integration tests verify payloads and headers before and after.

## 16. Key Takeaways

- `ProducerInterceptor` runs before serialization; modifying key/value changes the bytes written to Kafka.
- `ConsumerInterceptor` runs before `poll()` returns records; filtering records here can cause the application to skip data while consumer position advances.
- Spring `RecordInterceptor` runs before the listener; it can return a different record or `null`, but a new record must preserve topic, partition, and offset.
- Use `RecordFilterStrategy` when you want to discard records rather than hiding business filtering inside an interceptor.
- Exceptions in Kafka `ProducerInterceptor`/`ConsumerInterceptor` are caught and logged; do not use them to block invalid data.
- Mutable payloads can be modified through references even though `ConsumerRecord`/`ProducerRecord` do not allow swapping the value reference directly.
- Kafka headers are mutable; only add/remove headers per an explicit contract.
- Interceptors may run concurrently; avoid shared mutable state and slow callbacks.
- Use serializers/converters/mappers for intentional payload conversions, and keep business logic in the application layer.
- Test payloads, keys, metadata, and headers before/after interceptors to prove there are no unexpected modifications.

To avoid unexpected payload modifications, keep interceptors focused on observation and scoped metadata enrichment. When data transformation is needed, perform it in a separately tested application mapper or serializer/converter. When records need to be dropped, use `RecordFilterStrategy` with an explicit commit policy; when returning a new record from `RecordInterceptor`, preserve Kafka positioning fields. These clear boundaries ensure events reach consumers with the exact content published by producers.

## References

- [Spring for Apache Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring for Apache Kafka — Filtering Messages](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/filtering.html)
- [Spring for Apache Kafka — Wiring Spring Beans into Producer/Consumer Interceptors](https://docs.spring.io/spring-kafka/reference/kafka/interceptors.html)
- [Spring Kafka — RecordInterceptor API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/RecordInterceptor.html)
- [Apache Kafka — ProducerInterceptor API](https://kafka.apache.org/42/javadoc/org/apache/kafka/clients/producer/ProducerInterceptor.html)
- [Apache Kafka — ConsumerInterceptor API](https://kafka.apache.org/42/javadoc/org/apache/kafka/clients/consumer/ConsumerInterceptor.html)

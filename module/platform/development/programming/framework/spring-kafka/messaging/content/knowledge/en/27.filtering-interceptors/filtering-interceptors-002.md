# Filtering Records Before the Listener

Not every record polled from Kafka by a consumer needs to enter business logic. For example, an application may only process order events belonging to the current tenant, skip test events, or exclude a notification type that the listener does not care about. Spring Kafka lets you filter records before invoking `@KafkaListener` using `RecordFilterStrategy`.

The filter runs in the listener container's processing flow. If the strategy marks a record for exclusion, the adapter discards the record and does not invoke the listener method for it. Therefore, a filter decision ends processing for that record in this consumer; it does not trigger retries or automatically route the record to a dead-letter topic (DLT).

## 1. How does RecordFilterStrategy work?

`RecordFilterStrategy<K, V>` is a Spring Kafka interface used to decide whether a `ConsumerRecord` should be discarded. The `filter()` method returns a boolean with the following meaning:

- `true`: discard the record; the listener does not receive this record.
- `false`: keep the record; continue invoking the listener as usual.

Spring Kafka wraps the listener in a filtering adapter to invoke the strategy before passing the record to the listener. The application does not need to poll the consumer manually or manage offsets itself just to filter records.

For example, a listener only processes real orders and skips events marked as test data:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.listener.RecordFilterStrategy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderFilterConfiguration {

    @Bean
    RecordFilterStrategy<String, OrderCreated> testOrderFilter() {
        return record -> {
            OrderCreated event = record.value();
            return event != null && event.testEvent();
        };
    }
}
```

In this example, records with a null payload are kept so the application decides how to handle them, while records with `testEvent()` equal to `true` are discarded. The name and structure of `OrderCreated` are illustrative; replace them with your application's event contract.

## 2. Configuring a filter on the listener container factory

You can attach a default `RecordFilterStrategy` for all listeners using the same factory via `setRecordFilterStrategy()`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.RecordFilterStrategy;

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
orderKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        RecordFilterStrategy<String, OrderCreated> testOrderFilter) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setRecordFilterStrategy(testOrderFilter);
    factory.setAckDiscarded(true);
    return factory;
}
```

`setAckDiscarded(true)` tells the filtering adapter to acknowledge discarded records when an appropriate `Acknowledgment` is present. The default value of `ackDiscarded` is `false`. Choose this setting together with the container's `AckMode` and transaction configuration; specifically test how offsets are committed when the listener uses manual acknowledgment. If discarded records should be treated as processed, ensure the acknowledgment configuration actually includes those record offsets in the commit flow.

The listener only needs to declare the factory:

```java
@KafkaListener(
        topics = "${app.kafka.orders-topic}",
        containerFactory = "orderKafkaListenerContainerFactory")
public void onOrder(OrderCreated event) {
    orderService.handle(event);
}
```

A factory with a shared filter is suitable when listeners in the group share the same rule. If each listener has its own criteria, you can select the filter at the annotation level.

## 3. Selecting a dedicated filter per @KafkaListener

Since Spring Kafka 2.8, `@KafkaListener` provides the `filter` attribute to specify the bean name of a `RecordFilterStrategy` for that listener. This is useful when multiple listeners share a single factory but require different filtering rules.

```java
@Bean
RecordFilterStrategy<String, OrderCreated> publicOrderFilter() {
    return record -> {
        OrderCreated event = record.value();
        return event == null || event.internalOnly();
    };
}

@KafkaListener(
        id = "public-order-listener",
        topics = "${app.kafka.orders-topic}",
        filter = "publicOrderFilter")
public void onPublicOrder(OrderCreated event) {
    orderService.publishToPublicView(event);
}
```

In this example, the `publicOrderFilter` filter excludes null payloads and internal-only events. The bean name in `filter` must match the registered Spring bean. The `filter` attribute requires Spring Kafka 2.8 or later; for older versions, configure the filter through the container factory.

When a listener has its own filter, verify how the filter is resolved alongside the listener's factory in the version you use. Avoid configuring multiple filters simultaneously under the assumption that they are automatically chained; clearly establish the final strategy used by the container.

## 4. What happens to discarded records?

Filtered records are not passed to the listener method. They have already been read from Kafka by the consumer, so the application must make an explicit decision regarding offset acknowledgment. `ackDiscarded` controls whether the filtering adapter acknowledges a discarded record when acknowledgment is available; actual committing still follows the configured `AckMode`, transaction setup, and container.

| Configuration | Meaning to verify |
| --- | --- |
| `ackDiscarded = false` | The adapter does not proactively acknowledge discarded records. With manual acknowledgment, determine who acknowledges the record and when the offset is committed. |
| `ackDiscarded = true` | The adapter acknowledges discarded records when an `Acknowledgment` is present; the container still commits according to the active acknowledgment mechanism. |

If discarded records are unneeded data that should not be redelivered after a restart, configure acknowledgment so offsets are intentionally confirmed. When unsure, test with the actual `AckMode.RECORD`, `BATCH`, `MANUAL`, or `MANUAL_IMMEDIATE` used by the application; do not infer the outcome merely from the listener not being invoked.

In containers using Kafka transactions, offset acknowledgment must participate in the transaction according to container configuration. Do not commit directly from inside the filter strategy. `RecordFilterStrategy` only decides whether to keep or discard a record, while the container manages offsets and transactions.

## 5. Filtering by payload, key, or headers

Filters can inspect multiple parts of a `ConsumerRecord`:

```java
@Bean
RecordFilterStrategy<String, OrderCreated> internalSourceFilter() {
    return record -> {
        var header = record.headers().lastHeader("source");
        if (header == null) {
            return false;
        }

        String source = new String(
                header.value(),
                java.nio.charset.StandardCharsets.UTF_8);
        return "internal-test".equals(source);
    };
}
```

This example discards records with the header `source=internal-test`. If the header does not exist, the filter keeps the record so the listener continues processing it. For key-based rules, you can check `record.key()`; for event-type rules, you can read an event type header or a discriminator field in the payload.

Explicitly define behavior when metadata is missing. Keeping the record by default is usually safer if a missing header could indicate an older producer or un-upgraded data. If the contract requires a mandatory header, you can discard the record or route it to a separate error path, but make that decision explicit.

## 6. Distinguishing filtering from error handling

Filtering and error handling solve two different problems:

| Situation | Appropriate mechanism |
| --- | --- |
| Valid record that the listener does not care about | `RecordFilterStrategy` |
| Record needs processing but encountered a transient failure | `DefaultErrorHandler` or retry topic |
| Payload cannot be deserialized | `ErrorHandlingDeserializer` and container error handler |
| Record violates the data contract or has a business error needing investigation | Validation in listener/service, then route through appropriate recovery/DLT |
| Need to observe, enrich metadata, or run logic before/after the listener | `RecordInterceptor` |

Do not use filters to hide data errors. For example, if `OrderCreated` is missing `orderId`, dropping the record via a filter can make the incident disappear from observability with no error record left to investigate. Validate data and throw an exception so the error handler/recoverer handles it if the record needs to be preserved.

Filtering is also unsuitable for transient conditions such as a busy payment service or unsynchronized inventory. If a record could become valid after a wait, use retry instead of discarding it.

## 7. Filtering and RecordInterceptor

`RecordInterceptor` is an extension point for logic running around listener invocation, such as recording metadata, tracing, or checking a lightweight condition. The `intercept()` method can return a record to proceed with invoking the listener; returning `null` skips the listener invocation for that record.

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.listener.RecordInterceptor;

RecordInterceptor<String, OrderCreated> tracingInterceptor =
        new RecordInterceptor<>() {
            @Override
            public ConsumerRecord<String, OrderCreated> intercept(
                    ConsumerRecord<String, OrderCreated> record,
                    Consumer<?, ?> consumer) {
                log.debug("Received record {}-{}@{}",
                        record.topic(), record.partition(), record.offset());
                return record;
            }
        };
```

Register the interceptor on the factory using `setRecordInterceptor()`. If the goal is solely to discard records based on a predicate, `RecordFilterStrategy` expresses that intent more clearly and has a dedicated `ackDiscarded` policy. Use interceptors for cross-cutting logic; avoid returning `null` as a substitute filter when before/after listener callbacks are not needed.

Do not call consumer APIs to arbitrarily commit or seek inside a filter or interceptor. Those operations can conflict with the container and make offsets unpredictable. Let the container manage the consumer lifecycle.

## 8. Principles for writing safe filters

Filters run on the consumer processing path, so they must be short, deterministic, and safe under concurrency:

1. Prefer inspecting the payload, key, and headers already present in the record.
2. Do not call REST endpoints, databases, or remote services inside a filter; slow operations reduce poll throughput and can trigger rebalances.
3. Do not cause side effects inside a filter. A filter may be invoked again when a record is redelivered.
4. Write stateless strategies or guarantee thread safety, because a factory can serve multiple listener threads.
5. Explicitly handle null payloads, null keys, and missing headers.
6. Do not use filters as an authorization mechanism. Access and tenant checks must be enforced in the appropriate security/business layer.
7. Record filter reasons using metrics or selective logging; avoid logging full sensitive payloads.

In particular, with compacted topics, a record with a null `value()` may be a tombstone used to delete a key from the compacted state. Do not mechanically discard tombstones if the consumer needs to maintain state or synchronize a data replica.

## 9. Observing and testing filtering

You should track metrics for total received records, kept records, discarded records, and errors within the filter. When logging discarded records, capture topic, partition, offset, key or event ID, and discard reason; logging the entire payload is unnecessary.

Integration tests should verify both listener behavior and offsets:

1. Send a record matching the filter; verify the listener is invoked once.
2. Send a record excluded by the filter; verify the listener is not invoked.
3. Test `ackDiscarded` with the active `AckMode` and verify whether discarded records are committed as required after a consumer restart.
4. Test null payloads, null keys, missing headers, and headers with invalid values.
5. When using `@KafkaListener(filter = "...")`, verify the right bean is selected for the listener.
6. When sharing a factory across multiple listeners, verify each listener receives the intended filtering strategy.
7. When tombstones exist, verify the filter keeps tombstones if business logic needs to process deletions.

## 10. Implementation checklist

- [ ] `RecordFilterStrategy.filter()` returns `true` for records to discard and `false` for records to keep.
- [ ] The filter is properly attached to the container factory or `@KafkaListener`'s `filter` attribute (Spring Kafka 2.8+).
- [ ] `ackDiscarded` aligns with `AckMode`, manual acknowledgment, and transactions.
- [ ] The filter makes no remote calls, produces no side effects, and does not block the consumer thread.
- [ ] Null payloads, null keys, missing headers, and tombstones have been accounted for.
- [ ] Data errors needing investigation go through validation/error handling instead of being silently dropped.
- [ ] Metrics/logs exist for discarded record counts and reasons.
- [ ] Listener invocation, offset commit, and post-restart behavior have been tested.

`RecordFilterStrategy` is a clear way to exclude records before invoking a listener. When filtering rules strictly reflect events the consumer does not need, and acknowledgment plus monitoring are properly configured, the application can reduce business processing overhead while maintaining offset control and visibility into discarded data.

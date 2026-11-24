# Processing individual records within a batch

When a consumer reads from Kafka, one `poll()` call can return multiple records across one or more partitions. Spring Kafka can deliver that entire group of records into a single `@KafkaListener` invocation. Applications can still process each record sequentially inside a loop while benefiting from batched delivery to cut listener invocation and coordination overhead.

This lesson focuses on configuring a batch listener, processing record by record, reporting errors at the exact position in the batch, and balancing batch size against processing time. Examples use the `OrderCreated` event; data types and services represent application domain components.

## 1. A batch is a delivery mechanism, not a single record

A producer can send events to a topic via `KafkaTemplate`. Kafka stores records in partitions and assigns each record its own offset. A consumer belonging to a consumer group receives its assigned partitions; each fetch can return multiple records. When batch mode is enabled, Spring Kafka passes that list of records to the listener.

Each element in the batch remains an independent `ConsumerRecord` carrying attributes such as:

- `topic()`: the topic containing the record.
- `partition()`: the partition containing the record.
- `offset()`: the record's position within that partition.
- `key()` and `value()`: the event's key and payload.
- `headers()`: metadata attached to the record.

A single batch can contain records from multiple partitions. Kafka guarantees ordering within each partition; do not infer a single global ordering across records from different partitions. When the listener iterates sequentially through the list, per-partition record order is preserved throughout that sequential processing.

## 2. Enabling the batch listener

Create a `ConcurrentKafkaListenerContainerFactory` for list-accepting listeners. The decisive configuration call is `setBatchListener(true)`. Without enabling this property, standard listeners receive one record at a time instead of a record list.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
class KafkaBatchConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    batchKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory,
            DefaultErrorHandler batchErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        factory.setCommonErrorHandler(batchErrorHandler);
        return factory;
    }

    @Bean
    DefaultErrorHandler batchErrorHandler() {
        // One initial attempt and up to two retries, spaced one second apart.
        return new DefaultErrorHandler(new FixedBackOff(1_000L, 2L));
    }
}
```

The listener references the configured factory via the `containerFactory` attribute:

```java
import java.util.List;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.listener.BatchListenerFailedException;
import org.springframework.stereotype.Component;

@Component
class OrderBatchListener {

    private final OrderService orderService;

    OrderBatchListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "${app.kafka.orders-topic}",
            containerFactory = "batchKafkaListenerContainerFactory")
    public void onMessage(List<ConsumerRecord<String, OrderCreated>> records) {
        for (int index = 0; index < records.size(); index++) {
            ConsumerRecord<String, OrderCreated> record = records.get(index);
            try {
                orderService.handle(record.value());
            }
            catch (Exception ex) {
                throw new BatchListenerFailedException(
                        "Failed to process OrderCreated event", ex, index);
            }
        }
    }
}
```

The loop processes each payload via the domain service. Keep `ConsumerRecord` rather than accepting only `List<OrderCreated>` whenever you need key, partition, offset, or headers for logging, source inspection, or diagnostics. In the example, `index` is the 0-based position of the record in the current list.

## 3. Handling errors at the exact record

In a batch listener, if a record fails after preceding records have been processed, the application needs to inform the container of the failure position. `BatchListenerFailedException` carries the failing record's index. When paired with `DefaultErrorHandler`, Spring Kafka can handle the succeeded portion of the batch and the portion to retry based on that position.

With proper configuration, the typical behavior is:

1. Records before the failed index are treated as processed and their offsets can be committed.
2. The failed record and subsequent records are sought so the container can re-receive and reprocess them.
3. `BackOff` controls the wait interval and retry count. Once retries are exhausted, the error handler's recoverer decides what to do with the unrecoverable record, such as logging or sending it to a dead-letter topic (DLT).

`FixedBackOff(1_000L, 2L)` in the example sets a one-second interval and up to two retries after the initial attempt. In real applications, configure a recoverer matching your data policy; if a DLT is needed, `DeadLetterPublishingRecoverer` can be paired with `KafkaTemplate` to route failed records to a separate topic.

If the listener throws an ordinary exception without identifying the failed position, the error handler may have to treat the entire batch as failed and reprocess it from the start. Records that already produced side effects prior to the failure can then be redelivered. Thus, reporting the exact failed index reduces duplicate processing, though it does not turn the batch into an atomic transaction.

### Avoid swallowing errors unintentionally

The following snippet appears to let the listener continue to the next record, but it swallows errors:

```java
for (OrderCreated event : events) {
    try {
        orderService.handle(event);
    }
    catch (Exception ex) {
        log.warn("Failed to process order", ex);
    }
}
```

If the listener finishes normally, the container may commit the batch. The failed record is then never retried; merely logging is not enough to guarantee data processing. Catch an exception and continue only when the application has completed an intentional recovery action, such as persisting the failed record to durable storage or successfully publishing to a DLT. Without such a mechanism, propagate the error to the container with an appropriate exception.

## 4. Offsets, side effects, and idempotency

Offsets belong to individual partitions, whereas a batch is simply the group of records delivered in one poll. With a batch listener, the default acknowledgment mode typically commits by batch after the listener completes successfully. A Java loop does not automatically create a separate commit per record. When using `BatchListenerFailedException` with `DefaultErrorHandler`, the container gains extra context to handle offsets before and after the failure point.

Committing a Kafka offset does not undo operations already executed in external systems. For example, suppose a listener updates the database for three orders and fails on the fourth; when the first three records are redelivered, those updates may run again. Design idempotent consumers, for instance:

- Use a stable event ID to detect already-processed events.
- Enforce unique constraints or use appropriate upsert operations in the database.
- Persist event processing state together with domain changes inside a single database transaction when possible.
- Acknowledge records only after business results have been durably saved.

If Kafka transactions must coordinate with a database, design transaction boundaries and recovery mechanisms explicitly. Do not treat receiving a list in a listener as a guarantee that all side effects in the list succeed or roll back together.

## 5. Batch size and throughput

Batching can reduce poll and listener-invocation overhead, yet every record still needs deserialization, validation, and business processing. With a sequential loop, batch processing duration roughly equals the sum of individual record processing times plus shared overhead.

Factors to monitor while tuning:

| Factor | Impact | Consideration |
| --- | --- | --- |
| `max.poll.records` | Caps maximum records a consumer fetches in one poll; actual batches may be smaller | Increase gradually while measuring processing duration, memory, and latency |
| `max.poll.interval.ms` | Maximum time allowed between `poll()` calls before a consumer may be deemed inactive | Ensure batch processing plus waits stay safely within this limit |
| Partition count | Determines maximum parallelism available across consumers in the same group | Provision enough partitions for desired concurrency and actual load |
| Listener container concurrency | Spawns multiple consumers/containers to process assigned partitions in parallel | Tune based on partition count, CPU, I/O, and target system capacity |
| Per-record processing time | One slow record can stretch total batch duration during sequential processing | Measure p95/p99, locate slow I/O calls, and set suitable timeouts |

Increasing `max.poll.records` does not guarantee higher throughput. Oversized batches can inflate memory usage, time before the next poll, and the number of records affected by a retry. If processing exceeds `max.poll.interval.ms`, the consumer may leave the group and trigger a rebalance.

Container concurrency lets multiple consumers in the same group process different partitions. A sequential loop inside one listener still handles elements of a batch one after another. If processing in parallel inside a batch, bound concurrent tasks, wait for all tasks to complete before the listener returns, aggregate errors per exact record, and preserve key/partition order if business logic requires it. Do not fire async tasks and return immediately, as the container may commit offsets before the work actually completes.

## 6. Choosing the right processing approach

Sequential element-by-element processing within a batch works well when an application wants to reduce delivery overhead while keeping clear per-record business logic. It is also convenient when reading per-record metadata and pinpointing the exact failing element.

A single-record listener fits better when each invocation needs an independent processing lifecycle, retry, or per-record acknowledgment. A batch listener fits better when an application needs to handle a group of items together or wants explicit control over batch boundaries. Base the decision on ordering rules, retry needs, side effects, and measured system throughput.

## 7. Implementation checklist

- [ ] Listener factory has `setBatchListener(true)` enabled.
- [ ] `@KafkaListener` references the right `containerFactory` and accepts an appropriate list type.
- [ ] Loop processes each record and retains metadata needed for observability and diagnostics.
- [ ] Errors are tied to the exact index via `BatchListenerFailedException` when per-record error handling is needed.
- [ ] `DefaultErrorHandler`, `BackOff`, and recoverer/DLT match the application's retry policy.
- [ ] Side effects tolerate record redelivery.
- [ ] `max.poll.records`, `max.poll.interval.ms`, and concurrency are tuned using measured metrics.
- [ ] If processing in parallel, the listener returns only after every task in the batch finishes.

When testing, send multiple records across both a single partition and multiple partitions, verify the listener receives a list, verify per-partition ordering, intentionally fail one record, and observe offsets, retries, and DLT behavior. Also test scenarios where an earlier record already produced side effects before the batch failed to confirm idempotency behaves correctly.

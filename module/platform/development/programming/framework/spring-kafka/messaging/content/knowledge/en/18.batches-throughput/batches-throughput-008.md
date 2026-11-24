# Single-record failure in a batch

When using Spring Kafka in batch mode, a single `@KafkaListener` invocation receives multiple records from one Kafka `poll()`. If processing one record fails and the listener throws an exception, the whole batch invocation is treated as failed. Therefore, error reporting must tell Spring Kafka exactly which record caused the failure; otherwise, the framework may have to redeliver the entire batch.

Spring Kafka 2.8 and later provide `BatchListenerFailedException` to indicate the failed record's position and `DefaultErrorHandler` to coordinate retries, recovery, or routing records to a dead-letter topic (DLT).

## 1. Why can one record cause a whole batch to be redelivered?

A batch listener typically receives `List<ConsumerRecord<K, V>>` or a converted list of payloads. Suppose a batch has four records and the third record is invalid. If the listener merely throws a `RuntimeException`, the error handler does not know which records succeeded and which need retrying. Without a position indicator, `DefaultErrorHandler` falls back to retrying the entire batch.

This directly impacts throughput. Already-processed records may run again, increasing processing time and creating duplicate side effects if business logic is not idempotent.

## 2. Reporting the exact failed record position

In a batch listener, catch errors inside the processing loop and throw `BatchListenerFailedException` with the record's index in the list. The index is `0`-based and must point to the exact element that failed.

```java
@KafkaListener(
    topics = "orders",
    groupId = "order-processor",
    containerFactory = "batchKafkaListenerContainerFactory")
public void consume(List<ConsumerRecord<String, OrderCreated>> records) {
    for (int index = 0; index < records.size(); index++) {
        ConsumerRecord<String, OrderCreated> record = records.get(index);
        try {
            orderService.process(record.value());
        } catch (RuntimeException ex) {
            throw new BatchListenerFailedException(
                "Cannot process record at batch index " + index, ex, index);
        }
    }
}
```

In this example, `index` is the position in the list passed to the listener, not the Kafka offset. An offset is the sequence number of a record within a partition; the batch index is the record's position in the current list. These two numbers can differ.

If the listener accepts `List<OrderCreated>` instead of `List<ConsumerRecord<String, OrderCreated>>`, the index must still match the payload's position in the list. Use `ConsumerRecord` when you need to log or inspect topic, partition, offset, and key as well.

Do not catch an exception, merely log it, and let the listener return as if processing succeeded. When the listener returns normally, the container may commit offsets under the active acknowledgement mode, silently skipping the failed record at the business layer.

## 3. Configuring retries and DLT with DefaultErrorHandler

`DefaultErrorHandler` is the common error handler for both record listeners and batch listeners in Spring Kafka 2.8+. For batch listeners, it uses `BatchListenerFailedException` to identify the failure position. You can configure backoff for transient errors and `DeadLetterPublishingRecoverer` to send unprocessable records to a DLT.

```java
@Bean
public DefaultErrorHandler batchErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {
    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
            dltTemplate,
            (record, exception) -> new TopicPartition(
                record.topic() + ".DLT", record.partition()));

    // Initial attempt, followed by up to 2 retries spaced 1 second apart.
    DefaultErrorHandler handler = new DefaultErrorHandler(
        recoverer, new FixedBackOff(1_000L, 2L));

    // Data errors that cannot be fixed by retrying go straight to the DLT.
    handler.addNotRetryableExceptions(InvalidOrderException.class);
    return handler;
}
```

Attach the handler to the batch-enabled container factory:

```java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        batchKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory,
            DefaultErrorHandler batchErrorHandler) {
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated> factory =
        new ConcurrentKafkaListenerContainerFactory<>();
    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setCommonErrorHandler(batchErrorHandler);
    return factory;
}
```

`FixedBackOff(1_000L, 2L)` means waiting one second between retry attempts and allowing two retries after the initial attempt. Match retry counts to the error type: brief network errors may benefit from retries, whereas malformed data or business-rule violations rarely fix themselves on retry.

In the DLT example, the record is sent to a topic with the `.DLT` suffix while keeping its source partition. The DLT topic therefore needs enough partitions to match all source partitions. The producer used by `KafkaTemplate` must also have serializers compatible with the keys and values routed to the DLT.

## 4. What happens to offsets when a record fails?

Kafka stores offsets separately per partition. A batch can contain records from multiple partitions, so offsets are committed per partition rather than via a single batch-wide sequence number.

| How the listener reports the error | How `DefaultErrorHandler` handles it |
| --- | --- |
| Throws `BatchListenerFailedException` with index | Commits progress for records preceding the failed record; seeks the failed record and remaining records so they are re-read. Once retries expire, the recoverer handles the failed record. |
| Throws another exception without identifying the failed record | Retries the whole batch via fallback handling. Once retries expire, invokes the recoverer for the records in the batch. |
| Catches error, logs only, and returns | Treats the listener as completed; the container proceeds to commit offsets per acknowledgement mode. The record may be skipped at the business layer. |

For example, suppose a partition has offsets `100`, `101`, `102`, `103`; the listener processes the first two records and fails at offset `102`. When the listener reports the exact index of the failed record, Spring Kafka can commit progress up to before offset `102` and seek to re-read starting from the failed record. Records `100` and `101` do not need to be reprocessed simply because `102` failed.

If the batch spans multiple partitions, remember that each partition tracks its own progress. Never compute a committed offset by adding one to a list element index.

## 5. Choosing retry, skip, or DLT

Classify errors by their ability to self-recover:

- **Transient errors:** timeouts, temporary disconnects to dependent services, or brief contention errors. Retry with backoff and a bounded attempt count.
- **Permanent data errors:** missing required fields, invalid values, or unconvertible payloads. Route to a DLT early for investigation and replay once data is fixed.
- **Programming errors:** unexpected nulls or invariant violations in code. Log thoroughly and alert; retrying repeatedly usually just slows down the consumer.

A DLT should preserve enough information for tracing: topic, partition, offset, key, payload, failure timestamp, and exception metadata added by the recoverer. When replaying from a DLT, enforce controlled workflows so the same event is not injected into the system multiple times.

## 6. Protecting business logic from duplicate processing

Retries are a normal part of messaging. A record can be redelivered after failures, rebalances, restarts, or when the consumer has not yet committed offsets. Therefore, business handlers should be idempotent: processing the same event multiple times produces the same final result.

Common techniques:

- Use a stable `eventId` and record processed markers using a unique constraint in the database.
- Perform data updates and record processed markers within the same database transaction.
- Confirm processing only after side effects are durably persisted.
- If publishing Kafka events from a database change, consider the transactional outbox pattern to avoid gaps between DB commits and Kafka publishes.

Kafka transactions can coordinate reading offsets and writing Kafka records inside a single Kafka transaction. They do not automatically make external database operations exactly-once. For containers with transactions enabled, listener errors typically flow through rollback handling and `DefaultAfterRollbackProcessor`; do not apply the `DefaultErrorHandler` setup above verbatim without verifying your application's transaction model.

## 7. Testing a single-record failure

A batch test should produce at least three records in the same partition: the first valid, the second failing, and the third valid. Then verify:

1. The listener reports the exact index of the second record using `BatchListenerFailedException`.
2. Records preceding the failure are not reprocessed once the handler has committed their progress.
3. The failed record is retried the configured number of times and routed to the DLT when retries exhaust or when non-retryable.
4. Records following the failure continue processing normally once the failed record is recovered.
5. When replaying the same `eventId`, business logic produces no duplicate side effects.

Embedded Kafka or Testcontainers can verify actual consumer, offset, and DLT behavior. Also test exceptions other than `BatchListenerFailedException`, as those can trigger whole-batch retries.

## 8. Operational signals to monitor

Monitor consumer lag per partition, processing duration per batch, retry counts, DLT volume, and batch failure rates. If a single failing record sharply degrades throughput, check whether the listener reports the exact index, whether backoff is overly long, and whether batch size is too large relative to the consumer's allowed processing window.

When increasing `concurrency`, the number of consumers in the same group cannot exceed the number of usefully assignable partitions. Batch listeners process batches per consumer; increasing concurrency does not eliminate a failing record and does not replace proper retry, DLT, and idempotency design.

## Conclusion

In batch listeners, pinpoint the failing record's position with `BatchListenerFailedException`. Combine `DefaultErrorHandler`, backoff, and a DLT to control retries; understand per-partition offsets to predict which records will be re-read. Finally, design idempotent processing so retries never corrupt business data.

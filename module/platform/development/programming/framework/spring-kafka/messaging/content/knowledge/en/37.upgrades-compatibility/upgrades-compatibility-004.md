# Error Handler Changes Across Versions

Spring Kafka has changed how containers handle listener errors across multiple versions. In older versions, record listeners and batch listeners used two separate interface families: `ErrorHandler` and `BatchErrorHandler`. Starting in Spring Kafka 2.8, the framework introduced `CommonErrorHandler` to unify these two flows; `DefaultErrorHandler` became the replacement for most legacy handlers. Starting in 2.9, the `CommonErrorHandler` API was refined further to more clearly express whether a handler handles only the failed record or seeks the remaining records itself.

When upgrading, do not just rename classes. You must re-check retry counts, backoff, seeks, offset commits, batch semantics, recoverers, DLT, and transaction rollbacks. A new handler may compile cleanly yet change the number of redeliveries or when offsets are committed if the old configuration is migrated inaccurately.

## 1. Distinguishing listener error handler and container error handler

Spring Kafka has two distinct error handling layers:

| Layer | Configuration | Scope |
|---|---|---|
| Listener-level | `@KafkaListener(errorHandler = "...")` and `KafkaListenerErrorHandler` | Handles errors bound to a listener method, receiving the converted `Message<?>` and `ListenerExecutionFailedException` |
| Container-level | `CommonErrorHandler` on the listener container/factory | Controls retry, redelivery, seek, recovery, offset commits, and errors occurring outside listener invocation |

The listener-level error handler has existed since Spring Kafka 2.0. It is suitable when a listener needs to produce a failure response, add logging, or apply custom logic at the converted message layer. This handler does not replace the container error handler. If you want the container to retry or send to a DLT using standard mechanisms, the listener-level handler must rethrow the exception so the container can handle it.

The container-level error handler is responsible for coordinating the consumer. This is the API area that changed significantly across 2.x, 3.x, and 4.x.

## 2. Key change timeline

| Spring Kafka version | Error handling changes |
|---|---|
| 2.0 | Added `errorHandler` on `@KafkaListener` to use `KafkaListenerErrorHandler` |
| 2.2 | Added `DeadLetterPublishingRecoverer`, expanding the ability to publish failed records to a dead-letter topic |
| 2.5 | `DefaultAfterRollbackProcessor`/error handlers support delivery attempt metadata; `RecoveringBatchErrorHandler` is an option for batch listeners |
| 2.7 | Introduced non-blocking retry via retry topics; converters can place the raw record into `KafkaHeaders.RAW_DATA` since 2.7 |
| 2.8 | Introduced `CommonErrorHandler`, `DefaultErrorHandler`, and unified handlers for record/batch; legacy factory setters deprecated, old interfaces retained for compatibility |
| 2.9 | Added `seekAfterError=false`, `BackOffHandler`; changed custom handler API from `handleRecord`/`remainingRecords` to `handleOne`/`seeksAfterHandling` and introduced new retry-state defaults |
| 3.x | Continues using `CommonErrorHandler`; legacy APIs marked deprecated for removal; added batch retry listener support and observation/lifecycle improvements per minor release |
| 4.x | Continues using `CommonErrorHandler`/`DefaultErrorHandler` for standard listener containers; check the migration guide and minor version APIs before upgrading |

These milestones are representative changes, not an exhaustive list of every change in every minor release. Always check against the exact Spring Kafka version selected by Spring Boot dependency management.

## 3. Error handling in versions prior to 2.8

Prior to 2.8, Spring Kafka split handlers by listener type. Record listeners used `ErrorHandler` and sub-interfaces such as `ConsumerAwareErrorHandler`; batch listeners used `BatchErrorHandler` along with consumer-aware/container-aware variants.

Common classes included:

| Legacy handler | Purpose |
|---|---|
| `LoggingErrorHandler` | Logs record errors and continues according to container behavior |
| `BatchLoggingErrorHandler` | Logs batch errors |
| `SeekToCurrentErrorHandler` | Seeks back to the failed record for redelivery after retry |
| `SeekToCurrentBatchErrorHandler` | Retries a batch via seek |
| `RecoveringBatchErrorHandler` | Retries a batch and invokes a recoverer when retries are exhausted |
| `RetryingBatchErrorHandler` | Retries a batch using a dedicated strategy |
| `ContainerStoppingErrorHandler` | Stops the listener container when an error occurs |
| `ConditionalDelegatingErrorHandler` | Selects a handler based on exception type |

In older versions, a factory could be configured with `setErrorHandler(...)` for record listeners and `setBatchErrorHandler(...)` for batch listeners. Two separate configurations made sharing a single factory for both record and batch listeners harder to standardize.

Legacy configuration example:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> orderFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setErrorHandler(
            new SeekToCurrentErrorHandler(new FixedBackOff(1_000L, 2L)));
    return factory;
}
```

This is an example for legacy codebases; `SeekToCurrentErrorHandler` is no longer the recommended choice when upgrading to 2.8+. Migrate to `DefaultErrorHandler` and `setCommonErrorHandler(...)`.

## 4. From 2.8: CommonErrorHandler unifies record and batch

Spring Kafka 2.8 introduced `CommonErrorHandler`, replacing both `ErrorHandler` and `BatchErrorHandler` for listener containers. A single factory can use the same common handler for both record listeners and batch listeners.

Provided implementations include:

| Common handler | Role |
|---|---|
| `DefaultErrorHandler` | Retries records/batches, seeks or redelivers, invokes a recoverer when retries are exhausted |
| `CommonLoggingErrorHandler` | Only logs errors; remaining records are handled according to handler semantics |
| `CommonContainerStoppingErrorHandler` | Stops the container when the listener fails |
| `CommonDelegatingErrorHandler` | Selects a delegate handler based on exception type |
| `CommonMixedErrorHandler` | Uses one handler for record listeners and another handler for batch listeners |

In 2.8, legacy interfaces were retained for compatibility; legacy factory setters such as `setErrorHandler(...)` and `setBatchErrorHandler(...)` were deprecated in favor of `setCommonErrorHandler(...)`. Starting in 3.0, legacy interfaces such as `ErrorHandler` and `BatchErrorHandler` were marked deprecated for removal. When writing new code or refactoring for an upgrade, use `CommonErrorHandler`.

## 5. Migrating SeekToCurrentErrorHandler to DefaultErrorHandler

`DefaultErrorHandler` is the most common direct replacement for `SeekToCurrentErrorHandler`. It inherits the failed record processor's retry/recovery mechanism and supports both record listeners and batch listeners.

New configuration example:

```java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L));
}

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> orderFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        DefaultErrorHandler orderErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(orderErrorHandler);
    return factory;
}
```

`FixedBackOff(1_000L, 2L)` means waiting 1 second between attempts and allowing 2 retries after the initial delivery: a total of up to 3 deliveries to the listener before recovery. The second argument is the number of additional retries, not the total number of delivery attempts.

If you only use `new DefaultErrorHandler()`, the current default backoff corresponds to 9 retries with no delay after the initial delivery; the record is recovered by logging when retries are exhausted. Do not assume the no-arg configuration matches your application's business retry policy.

## 6. Legacy handler migration table

Documented Spring Kafka replacements:

| Legacy handler | Replacement handler |
|---|---|
| `LoggingErrorHandler` | `CommonLoggingErrorHandler` |
| `BatchLoggingErrorHandler` | `CommonLoggingErrorHandler` |
| `ConditionalDelegatingErrorHandler` | `CommonDelegatingErrorHandler` |
| `ConditionalDelegatingBatchErrorHandler` | `CommonDelegatingErrorHandler` |
| `ContainerStoppingErrorHandler` | `CommonContainerStoppingErrorHandler` |
| `ContainerStoppingBatchErrorHandler` | `CommonContainerStoppingErrorHandler` |
| `SeekToCurrentErrorHandler` | `DefaultErrorHandler` |
| `RecoveringBatchErrorHandler` | `DefaultErrorHandler` |
| `SeekToCurrentBatchErrorHandler` | No direct replacement class; use `DefaultErrorHandler` with an infinite `BackOff` if unlimited retries are desired |
| `RetryingBatchErrorHandler` | No direct replacement class; use `DefaultErrorHandler` and throw an exception other than `BatchListenerFailedException` to trigger whole-batch retry |

Do not rename classes mechanically. For example, `RetryingBatchErrorHandler` may have retried the whole batch under its own semantics; `DefaultErrorHandler` distinguishes `BatchListenerFailedException` (identifying the failed record) from other exceptions (falling back to retrying the complete batch). Inspect listener code to pick the right semantics.

## 7. Switching factory configuration to setCommonErrorHandler

For code that creates listener container factories manually, replace the old setters with `setCommonErrorHandler(...)`:

```java
// Old: Spring Kafka prior to 2.8
factory.setErrorHandler(oldRecordErrorHandler);
factory.setBatchErrorHandler(oldBatchErrorHandler);

// New: Spring Kafka 2.8+
factory.setCommonErrorHandler(defaultErrorHandler);
```

When both record and batch listeners share a factory, `DefaultErrorHandler` can handle both. If the two listener types need different strategies, use `CommonMixedErrorHandler` or separate the listener container factories by purpose.

Do not configure both legacy setters and a common handler on the same factory expecting them to stack. During migration, remove the old configuration once the common handler is wired and tested.

## 8. Spring Boot auto-configuration and custom factories

If using the listener factory auto-configured by Spring Boot, you can declare a `CommonErrorHandler` bean; Boot attaches that bean to the auto-configured factory as supported by Spring Kafka.

```java
@Bean
CommonErrorHandler commonErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
    var handler = new DefaultErrorHandler(
            recoverer, new FixedBackOff(500L, 3L));
    handler.addNotRetryableExceptions(InvalidOrderException.class);
    return handler;
}
```

If the application defines its own `ConcurrentKafkaListenerContainerFactory`, call `factory.setCommonErrorHandler(handler)` directly as shown earlier. Do not assume an error handler bean is automatically attached to custom factories.

With multiple factories, name beans clearly and configure handlers per factory. One factory for events might need short retries; another for batch imports might need whole-batch retries or stopping the container to preserve data integrity.

## 9. Custom CommonErrorHandler API differences between 2.8 and 2.9+

This is a change that easily breaks source compatibility when upgrading from 2.8 to 2.9 or 3.x.

### Spring Kafka 2.8

In the 2.8 API, a custom `CommonErrorHandler` has these methods:

- `handleRecord(...)`: handles only the failed record when `remainingRecords()` returns `false`.
- `handleRemaining(...)`: handles the failed record along with remaining records from the poll when `remainingRecords()` returns `true`.
- `remainingRecords()`: indicates whether the handler receives only the failed record or all remaining records.
- `handleBatch(...)`: handles batch listener errors.
- `handleOtherException(...)`: handles errors not tied to a specific record, such as exceptions thrown during `poll()`.

### Spring Kafka 2.9 and higher

Starting in 2.9, the API was renamed to express semantics more clearly:

| 2.8 API | 2.9+ API | Meaning |
|---|---|---|
| `handleRecord(...)` | `handleOne(...)` | Handles only the failed record |
| `remainingRecords()` | `seeksAfterHandling()` | Whether the handler itself seeks the failed/remaining records |
| `handleRemaining(...)` | `handleRemaining(...)` | Still used when the handler itself processes the remaining record list |
| `handleBatch(...)` | `handleBatch(...)` | Handles batch errors |
| `handleOtherException(...)` | `handleOtherException(...)` | Handles errors without a record |

The old `handleRecord()` and `remainingRecords()` methods were deprecated in 2.9 and replaced by `handleOne()` and `seeksAfterHandling()`. Therefore, a custom handler written for 2.8 may still compile in some 2.9 releases via the deprecated methods, but should be migrated to the new API before upgrading further.

## 10. Migrating a record-only custom ErrorHandler

If an old custom handler implemented `ErrorHandler` or `ConsumerAwareErrorHandler`, migration in 2.8 usually meant implementing `handleRecord(...)` and `handleOtherException(...)`. If the handler only processes the failed record, `remainingRecords()` stays `false` (default).

Skeleton example for the 2.8 API:

```java
class AuditCommonErrorHandler implements CommonErrorHandler {

    @Override
    public void handleRecord(
            Exception exception,
            ConsumerRecord<?, ?> record,
            Consumer<?, ?> consumer,
            MessageListenerContainer container) {

        auditService.recordFailure(record, exception);
        throw new KafkaException("Record has not been recovered", exception);
    }

    @Override
    public void handleOtherException(
            Exception exception,
            Consumer<?, ?> consumer,
            MessageListenerContainer container,
            boolean batchListener) {

        throw new KafkaException("Consumer error outside listener", exception);
    }
}
```

This is an illustrative skeleton for the 2.8 branch; `auditService` is a dependency injected in a real application. The handler records an audit entry and throws an exception so the container does not treat the record as successfully processed. If you want to recover/skip the record, have explicit commit/recovery rules rather than just logging and returning.

In 2.9+, replace `handleRecord(...)` with `handleOne(...)` and return `false` if you want the container to resubmit the failed record to the listener after the handler finishes, or `true` if the handler has processed/recovered the record. Skeleton example for the new API:

```java
class AuditCommonErrorHandler implements CommonErrorHandler {

    @Override
    public boolean handleOne(
            Exception exception,
            ConsumerRecord<?, ?> record,
            Consumer<?, ?> consumer,
            MessageListenerContainer container) {

        auditService.recordFailure(record, exception);
        return false; // container will resubmit the failed record
    }

    @Override
    public void handleOtherException(
            Exception exception,
            Consumer<?, ?> consumer,
            MessageListenerContainer container,
            boolean batchListener) {

        throw new KafkaException("Consumer error outside listener", exception);
    }
}
```

Do not treat these two snippets as a single multi-version class: their signatures and return semantics differ. Compile against the exact Spring Kafka dependency of the target branch.

## 11. Migrating RemainingRecordsErrorHandler

The legacy `RemainingRecordsErrorHandler` receives the list of unprocessed records and usually performs seeks itself so those records are polled again.

In the 2.8 API:

- Implement `handleRemaining(...)`.
- Override `remainingRecords()` to return `true`.
- Implement `handleOtherException(...)` for non-record errors.

In the 2.9+ API:

- Continue implementing `handleRemaining(...)`.
- Override `seeksAfterHandling()` to return `true` because the handler performs the seeks itself.
- Implement `handleOtherException(...)`.

If the handler does not seek itself and wants the container to manage redelivery, use record-only semantics (`handleRecord`/`handleOne`) instead of falsely declaring that the handler seeks. Reporting the wrong semantics can cause records to be skipped or redelivered out of order.

## 12. Migrating a custom BatchErrorHandler

A custom `BatchErrorHandler` is migrated to `CommonErrorHandler` by implementing `handleBatch(...)` and `handleOtherException(...)`. A batch handler receives the full `ConsumerRecords` from a poll; if you want to retry a specific record, throw `BatchListenerFailedException` in the listener and let `DefaultErrorHandler` handle it.

If implementing `handleBatch` manually, explicitly decide:

- Which offsets should partitions be seeked to?
- Will the entire batch or only the remaining subset be retried?
- When recovering a failed record, where is its offset committed?
- If DLT publishing fails, will the record be redelivered?
- Is the consumer paused/resumed properly during backoff?
- Is the batch listener running inside a transaction?

Do not call seek inside a listener-level `KafkaListenerErrorHandler`; the container is unaware a seek occurred. With a container-level `CommonErrorHandler`, if you control seeks yourself, declare `seeksAfterHandling()` accurately and handle the remaining records too.

## 13. DefaultErrorHandler and seekAfterError

By default, `DefaultErrorHandler` uses seek to instruct the consumer to re-read the failed record and any remaining records that need redelivery. Starting in Spring Kafka 2.9, you can set `seekAfterError=false`.

When `seekAfterError=false`:

1. The container retains the unprocessed records.
2. The error handler determines which records need to be re-sent to the listener.
3. The container performs a paused poll to keep the consumer/group alive.
4. Remaining records are re-sent to the listener without seeking the consumer back to the old offset.

This mode can be useful when you do not want to alter the consumer position via seeks, though it does not eliminate retry cost and does not automatically solve duplicate side effects. Test record listeners, batch listeners, and pause duration before enabling it.

```java
DefaultErrorHandler handler =
        new DefaultErrorHandler(new FixedBackOff(500L, 2L));
handler.setSeekAfterError(false); // Spring Kafka 2.9+
```

Do not copy `setSeekAfterError(false)` into 2.8 code; this property was added in 2.9.

## 14. BackOffHandler and long retry delays

Prior to 2.9, error handlers typically waited out backoff on the consumer thread. Starting in 2.9, you can configure a `BackOffHandler`; the framework provides `ContainerPausingBackOffHandler` to pause the container during backoff instead of keeping the thread asleep the entire time.

```java
@Bean
ListenerContainerPauseService listenerContainerPauseService(
        ListenerContainerRegistry registry,
        TaskScheduler taskScheduler) {

    return new ListenerContainerPauseService(registry, taskScheduler);
}

@Bean
DefaultErrorHandler longBackOffErrorHandler(
        ConsumerRecordRecoverer recoverer,
        ListenerContainerPauseService pauseService) {

    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(60_000L, 2L),
            new ContainerPausingBackOffHandler(pauseService));
}
```

This example uses a long 60-second backoff. `ListenerContainerPauseService` needs a `TaskScheduler` and the listener container registry; ensure the application has a suitable scheduler. Actual pause timing granularity depends on `pollTimeout`; the container must continue polling appropriately to maintain group membership. `ContainerPausingBackOffHandler` is useful when delays exceed `max.poll.interval.ms`, but verify processing times, heartbeats, and rebalances in a realistic environment.

## 15. Retry state changes when exception type changes

Retry state is tracked per record/partition/offset. Starting in Spring Kafka 2.9, `resetStateOnExceptionChange` defaults to `true` for the failed record processor: if the exception type changes between delivery attempts, the retry sequence restarts and a different backoff may be chosen.

In versions prior to 2.9, exception types were not considered by default. If upgrading an application that relies on the retry counter continuing regardless of exception type, verify the behavior and consider setting it explicitly:

```java
handler.setResetStateOnExceptionChange(false);
```

For the batch processor, the default may differ from the failed record processor in some newer versions to preserve backward compatibility. Check the Javadoc and change history of the specific version before assuming identical defaults for record and batch.

## 16. Classifying retryable and non-retryable exceptions

By default, `DefaultErrorHandler` treats certain errors as fatal because retrying usually cannot fix malformed data or contract mismatches. Default non-retryable exceptions include:

- `DeserializationException`
- `MessageConversionException`
- `ConversionException`
- `MethodArgumentResolutionException`
- `NoSuchMethodException`
- `ClassCastException`

For these errors, the recoverer is invoked immediately on the first failure. You can add business exceptions to the non-retryable group:

```java
DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, new FixedBackOff(1_000L, 3L));

handler.addNotRetryableExceptions(
        InvalidOrderException.class,
        UnsupportedEventVersionException.class);
```

If you want to define the full classification, use `setClassifications(...)` with a map and an appropriate default classification. Avoid configuring every exception as retryable: permanent validation errors will keep the partition busy and increase lag.

Distinguish transient technical exceptions (database timeouts, service unavailable) from data/contract errors (missing fields, unsupported event versions). Retries are only helpful for errors that can resolve themselves after some time.

## 17. Retry count and default behavior

Read `BackOff` parameter meanings carefully when upgrading:

| Configuration | Total times the listener can receive the record |
|---|---:|
| `new FixedBackOff(0L, 0L)` | 1 time, no retries |
| `new FixedBackOff(1_000L, 2L)` | 3 times: 1 initial + 2 retries |
| `new FixedBackOff(1_000L, 5L)` | 6 times: 1 initial + 5 retries |
| `FixedBackOff.UNLIMITED_ATTEMPTS` | Unlimited retries |

When retries are exhausted, the recoverer is invoked. If you use the no-argument constructor of `DefaultErrorHandler`, the default backoff in current versions is typically 9 retries with no delay, followed by the default recoverer logging the record.

If `SeekToCurrentErrorHandler` was previously configured with max failures, convert that to the number of additional retries rather than copying the integer directly without checking how the old constructor counted attempts.

## 18. Recoverer and DeadLetterPublishingRecoverer

When retries are exhausted, the recoverer decides where the failed record goes. `DefaultErrorHandler` can accept a `ConsumerRecordRecoverer`, such as `DeadLetterPublishingRecoverer` to publish failed records to a dead-letter topic.

```java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(kafkaTemplate,
                (record, exception) ->
                        new TopicPartition(
                                record.topic() + ".dlt",
                                record.partition()));

DefaultErrorHandler handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L));
```

The resolver above sends records to `<source-topic>.dlt` on the same partition as the source. If using the default routing of `DeadLetterPublishingRecoverer`, the default topic name is `<source-topic>-dlt` and the target partition is the source partition. Therefore, the DLT must have at least as many partitions as the source topic when preserving the partition number.

DLT records usually carry source metadata such as original topic, partition, offset, timestamp, and exception headers. Preserve these headers for investigation, replay, or data repair. If the DLT topic has fewer partitions than the source and the resolver requests the same partition, publishing will fail.

## 19. Recovery failures must also be factored into migration

If the recoverer throws an exception, the failed record is not considered successfully recovered. The record enters the handler's redelivery/seek path. Since 2.5.5, when recovery fails, the backoff state is reset by default so subsequent delivery attempts go through backoff again before retrying recovery.

To revert to the old behavior (not resetting backoff after recovery failure), configure:

```java
handler.setResetStateOnRecoveryFailure(false);
```

Do not mark an offset as processed simply because the recoverer was called. Check the DLT send result and the offset commit policy after successful publishing.

## 20. AckAfterHandle and commitRecovered

These two properties answer different questions:

- `ackAfterHandle`: whether the container commits the offset when the error handler returns normally (treating the error as handled). Defaults to `true`.
- `commitRecovered`: allows committing the offset of a recovered record when using `AckMode.MANUAL_IMMEDIATE`; must be explicitly configured when using manual immediate.

Example:

```java
DefaultErrorHandler handler = new DefaultErrorHandler(
        recoverer, new FixedBackOff(1_000L, 2L));
handler.setAckAfterHandle(true);
handler.setCommitRecovered(true);
```

Do not enable `commitRecovered` just because a listener uses `MANUAL`; this property is for `MANUAL_IMMEDIATE`. If the handler does not throw an exception after recovering, offset commits also depend on `ackAfterHandle` and the container's AckMode. Test committed offsets, not just whether the recoverer was invoked.

## 21. Batch listener: BatchListenerFailedException

With a batch listener, the framework does not automatically know which record in the batch caused the listener to fail if the listener just throws a generic exception. For `DefaultErrorHandler` to handle individual records, the listener should throw `BatchListenerFailedException` with the failed record or its index.

```java
@KafkaListener(topics = "orders", containerFactory = "batchFactory")
public void listen(List<ConsumerRecord<String, OrderEvent>> records) {
    for (ConsumerRecord<String, OrderEvent> record : records) {
        try {
            orderService.process(record.value());
        }
        catch (Exception ex) {
            throw new BatchListenerFailedException(
                    "Failed to process order", ex, record);
        }
    }
}
```

When the failed record is identified, `DefaultErrorHandler` can commit preceding records, retry the failed record and remaining records, and once retries are exhausted, recover the failed record and continue with subsequent records. For POJO batch listeners without `ConsumerRecord`, pass the index of the failed record to `BatchListenerFailedException`.

If a batch listener throws an exception other than `BatchListenerFailedException`, the handler falls back to retrying the complete batch. The batch is held in memory and the listener is invoked again; there is no guarantee that batch redelivery has the same record count or order in every case as re-reading from the broker.

## 22. Difference between whole-batch retry and single-record retry

| How the listener reports the error | `DefaultErrorHandler` behavior |
|---|---|
| Throws `BatchListenerFailedException` with record/index | Pinpoints failure; commits prior records, retries failed/remaining records, recovers the failed record when retries are exhausted |
| Throws another exception | Falls back to retrying the complete batch in memory; when retries are exhausted, recovers the batch's records |
| Recoverer fails | Does not consider the record recovered; batch/record is redelivered per error handler |

The fallback batch handler pauses the consumer, keeps polling to keep the consumer alive during backoff, and re-invokes the listener with the held batch. This complete-batch retry mechanism cannot be used with transactions. If the application requires transactions, design rollback/retry via `AfterRollbackProcessor`.

## 23. Delivery attempt header

Since Spring Kafka 2.5, error handlers support delivery attempt metadata via `KafkaHeaders.DELIVERY_ATTEMPT`. This header increments starting at 1 and is only added when the container property `deliveryAttemptHeader` is enabled.

With a raw `ConsumerRecord`, the header value is encoded as 4 bytes; it can be read via:

```java
int attempt = ByteBuffer.wrap(record.headers()
        .lastHeader(KafkaHeaders.DELIVERY_ATTEMPT).value())
        .getInt();
```

With `@KafkaListener`, if supported by the header mapper, you can inject:

```java
public void listen(
        OrderEvent event,
        @Header(KafkaHeaders.DELIVERY_ATTEMPT) int attempt) {
    // log attempt or add metric
}
```

Since 3.3, a batch listener wanting delivery attempt headers populated on `ConsumerRecord` must register `DeliveryAttemptAwareRetryListener` as a retry listener on `DefaultErrorHandler`. Do not assume batch listeners receive the header the same way record listeners did in older versions.

## 24. Retry listeners and observing recovery

`RetryListener` receives notifications when a record/batch fails, is recovered, or recovery fails. Since 2.8.10, callbacks for batch listeners were also added.

```java
DefaultErrorHandler handler = new DefaultErrorHandler(
        recoverer, new FixedBackOff(1_000L, 2L));

handler.setRetryListeners(new RetryListener() {
    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception exception,
            int deliveryAttempt) {
        metrics.retryFailed(record.topic(), exception.getClass().getSimpleName());
    }

    @Override
    public void recovered(ConsumerRecord<?, ?> record, Exception exception) {
        metrics.recovered(record.topic());
    }

    @Override
    public void recoveryFailed(
            ConsumerRecord<?, ?> record,
            Exception original,
            Exception recoveryFailure) {
        metrics.recoveryFailed(record.topic());
    }
});
```

Illustrative example; `metrics` is an application service. When upgrading, check the interface of your version because batch callbacks were added in 2.8.10 and later minor versions may expand the API further.

## 25. Blocking retry vs. non-blocking retry topics

`DefaultErrorHandler` performs retries inside the consumer processing flow; this is often called blocking retry. The consumer/partition is affected by the backoff and retry duration. Non-blocking retry was introduced in Spring Kafka 2.7 via `@RetryableTopic`/retry topics: the record is published to a delayed retry topic and processed later by another listener.

The two mechanisms solve different problems:

| Characteristic | `DefaultErrorHandler` | `@RetryableTopic` |
|---|---|---|
| Retry | Inside the current topic's consumer flow | Published to retry topic and consumed again after delay |
| Ordering | Can preserve partition ordering during blocking retry | Can alter ordering across events with the same key |
| Partition impact | Partition can be held up during retries | Failed event is offloaded to another topic |
| Supports batch listener | Yes | Does not support batch listeners |
| Best fit | Short-lived errors, ordering required | Long delays, non-blocking and altered ordering acceptable |

Do not convert every `DefaultErrorHandler` to `@RetryableTopic` just to avoid blocking. Evaluate event ordering, retry topic topology, retention, DLT, consumer counts, and replay capability.

## 26. Transactions and AfterRollbackProcessor

When a listener container uses Kafka transactions, Spring Kafka by default does not configure a container error handler to swallow exceptions; exceptions are thrown so the transaction rolls back. Post-rollback handling belongs to `AfterRollbackProcessor`, typically `DefaultAfterRollbackProcessor`.

If you attach a custom `CommonErrorHandler` to a transactional container and the handler returns normally, the container may treat the error as handled and the transaction will not roll back as intended. If you want a rollback, the custom handler must throw an exception out.

Basic flow:

```text
Listener processes record
       |
       +-- success --> commit transaction and offset
       |
       +-- exception --> rollback transaction
                         |
                         v
                  AfterRollbackProcessor
                         |
                         +--> redelivery/retry
                         |
                         +--> recover/DLT when retries exhausted
```

Do not use in-memory fallback batch retry as a substitute for transaction rollback; Spring Kafka documentation explicitly notes that fallback batch retry cannot be used with transactions.

## 27. Listener-level KafkaListenerErrorHandler

`KafkaListenerErrorHandler` is not replaced by `CommonErrorHandler`. It remains a method-level handler selected via the `errorHandler` attribute on `@KafkaListener`.

```java
@Component
public class OrderListenerErrorHandler implements KafkaListenerErrorHandler {

    @Override
    public Object handleError(
            Message<?> message,
            ListenerExecutionFailedException exception) throws Exception {

        // Log application-level context then let the container retry/recover.
        throw exception;
    }
}

@KafkaListener(
        topics = "orders",
        errorHandler = "orderListenerErrorHandler")
public void listen(OrderEvent event) {
    orderService.process(event);
}
```

If a listener-level handler returns normally instead of throwing, the exception may not propagate to the container; the container then will not perform retries as expected. The return value of `KafkaListenerErrorHandler` is ignored; the handler is typically used to rethrow the original exception or throw a new one.

Do not call `consumer.seek(...)` inside `KafkaListenerErrorHandler` or its consumer-aware variants. The container does not know a seek occurred inside the handler and may manage offsets incorrectly.

## 28. Poll-level exceptions and handleOtherException

Not every error is tied to a `ConsumerRecord`. For example, consumer `poll()` can throw an exception before returning any records. `CommonErrorHandler.handleOtherException(...)` handles this category of errors.

When migrating custom handlers, do not only implement `handleOne()`/`handleRemaining()`/`handleBatch()` and omit `handleOtherException()`. Have a policy for consumer-level errors: log and stop the container, throw to stop the container, or handle according to specific recovery capabilities.

Without a record, you cannot send a specific record to a DLT using a normal recoverer. Distinguish poll/network/authorization errors from listener errors on a single record.

## 29. Deserialization failures and ErrorHandlingDeserializer

Deserialization can fail before the listener receives the payload. If you want the error handler to process failed records and publish to a DLT, you usually need to wrap the real deserializer with `ErrorHandlingDeserializer` so the exception is placed in a header instead of causing `poll()` to fail without normal records.

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
```

Illustrative configuration for JSON values; add type mappings/trusted packages matching your real model. `DefaultErrorHandler` treats deserialization/conversion exceptions as fatal by default because retrying rarely makes a malformed payload valid. When using a batch listener, the application must inspect the conversion/deserialization failure header and throw `BatchListenerFailedException` with the exact index so the handler knows which record failed.

## 30. Using CommonDelegatingErrorHandler after migration

If you previously used a conditional delegating handler, you can migrate to `CommonDelegatingErrorHandler`. It selects a handler by exception type. Delegates must have compatible properties such as `ackAfterHandle` and `seekAfterError`.

```java
DefaultErrorHandler retryHandler = new DefaultErrorHandler(
        recoverer, new FixedBackOff(500L, 3L));

CommonContainerStoppingErrorHandler stopHandler =
        new CommonContainerStoppingErrorHandler();

Map<Class<? extends Throwable>, CommonErrorHandler> delegates =
        new LinkedHashMap<>();
delegates.put(FatalInfrastructureException.class, stopHandler);

CommonDelegatingErrorHandler handler =
        new CommonDelegatingErrorHandler(retryHandler);
handler.setErrorHandlers(delegates);
```

This example stops the container on severe infrastructure errors and uses retry/recovery for ordinary errors. `LinkedHashMap` makes delegate lookup order deterministic. Ensure the handlers have compatible ack/seek semantics; do not combine a self-seeking handler with a non-seeking handler without understanding the impact.

## 31. CommonMixedErrorHandler for record and batch

If the same factory must support both record listeners and batch listeners with different handlers for each type, use `CommonMixedErrorHandler`:

```java
CommonErrorHandler recordHandler =
        new DefaultErrorHandler(recordRecoverer, new FixedBackOff(500L, 2L));

CommonErrorHandler batchHandler =
        new DefaultErrorHandler(batchRecoverer, new FixedBackOff(1_000L, 1L));

factory.setCommonErrorHandler(
        new CommonMixedErrorHandler(recordHandler, batchHandler));
```

Both handlers can use different backoffs/recoverers, but you must still verify compatibility of shared properties and batch listener behavior. If the differences are substantial, splitting factories is usually easier to operate and observe.

## 32. Changes to review when upgrading from 2.7 to 2.8

Checklist for moving from legacy handlers to common handlers:

1. Find all classes implementing `ErrorHandler`, `BatchErrorHandler`, and their sub-interfaces.
2. Find all calls to `setErrorHandler(...)` or `setBatchErrorHandler(...)`.
3. Replace standard handlers with the corresponding classes in the migration table.
4. Migrate custom handlers to `CommonErrorHandler`.
5. Implement `handleOtherException(...)` for poll/consumer errors.
6. Verify whether the handler processes only the failed record or all remaining records.
7. Check `ackAfterHandle` and offset commits after recovery.
8. Test record listeners and batch listeners separately.
9. If using transactions, verify exceptions still roll back transactions.
10. Run DLT tests and verify destination partitions.

## 33. Changes to review when upgrading from 2.8 to 2.9/3.x

1. Replace `handleRecord(...)` with `handleOne(...)` in custom handlers.
2. Replace `remainingRecords()` with `seeksAfterHandling()`.
3. Review `seekAfterError` and decide whether to use non-seeking mode.
4. Check `resetStateOnExceptionChange` because the default changed in 2.9.
5. For long backoffs, consider `ContainerPausingBackOffHandler`.
6. Check `RetryListener` batch callbacks if needed for observability.
7. Check retry counts: additional retries vs. total delivery attempts.
8. Verify batch listeners throw `BatchListenerFailedException` with the right record/index.
9. Verify listener-level error handlers do not accidentally swallow exceptions.
10. Re-run integration tests against a broker to verify actual seeks/commits.

## 34. Changes to review when upgrading from 3.x to 4.x

For standard listener error handling, `CommonErrorHandler` and `DefaultErrorHandler` remain central in Spring Kafka 4.x. Do not view upgrading to 4.x as a reason to go back to legacy `ErrorHandler`/`BatchErrorHandler`. However, 4.x comes with foundational changes in Spring Framework, Spring Boot, Java, and the Kafka client; upgrade according to your application's compatibility matrix.

When verifying error handling in 4.x:

- Confirm the Spring Kafka version managed by the Spring Boot BOM.
- Recompile custom `CommonErrorHandler` implementations against the 4.x API.
- Check deprecated/removed classes in the deprecated list for the exact minor version.
- Check serializers/deserializers and related dependencies because Jackson 3 is a notable change in the 4.x line.
- Run integration tests against a compatible broker version.
- Verify transaction rollbacks, DLT publishing, retry topics, and consumer group behavior after upgrading.

Do not deduce that a specific API was removed solely from the major version number. Use the Javadoc/deprecated list of the actual artifact to confirm whether a method/class still exists.

## 35. Post-migration test matrix

| Test case | What must be verified |
|---|---|
| Record listener succeeds | Offset commits according to current AckMode |
| Record listener transient error | Retries the exact count and backoff |
| Non-retryable exception | Recovers immediately per classification |
| Retries exhausted | Recoverer is called once for a successful recovery |
| DLT publish succeeds | Record has complete original topic/partition/offset/exception headers |
| DLT publish fails | Record is not marked recovered and is redelivered per policy |
| BatchListenerFailedException | Commits prior records, retries/recovers the failed record and remaining records |
| Generic batch exception | Fallback retries the complete batch with proper semantics |
| `seekAfterError=false` | Unprocessed records are resubmitted properly and consumer keeps polling |
| Poll-level exception | `handleOtherException` is called and container exhibits expected behavior |
| Manual immediate ack | `commitRecovered` works properly if enabled |
| Transaction rollback | Exception is not swallowed by handler and transaction rolls back |
| Listener-level handler | Rethrowing triggers container retry; does not seek consumer directly |
| Retry topic | Ordering, delay, retry topics, and DLT match the contract |
| Restart/rebalance | No lost records; duplicates are handled idempotently |

## 36. Common migration issues

| Symptom | Common cause | Resolution |
|---|---|---|
| Fails to compile after 2.9 upgrade | Custom handler still uses `handleRecord`/`remainingRecords` | Migrate to `handleOne`/`seeksAfterHandling` |
| Factory does not pick up new handler | Still calling legacy setter or configuring the wrong factory | Use `setCommonErrorHandler` on the factory actually used by the listener |
| Record skipped after handler logs error | Handler returns normally so offset is acked after handling | Only return when recovered; if unhandled, throw exception or return resubmit semantics |
| More retries than expected | Confusing retry count with total delivery attempts | Count initial delivery + additional retries |
| Repeated DLT publish failures | Invalid topic/partition/serializer/ACL | Check destination resolver, partition count, serializer, and WRITE permissions |
| Entire batch retried unexpectedly | Listener throws generic exception instead of `BatchListenerFailedException` | Specify failed record/index if retrying from that record is desired |
| Transaction does not roll back | Custom handler swallowed the exception | Throw exception out so the transaction rolls back |
| Consumer does not receive record again after retry | Declared wrong seek semantics or committed offset too early | Check `seeksAfterHandling`, AckMode, and committed offset |
| Long retry delay causes rebalance | Consumer thread blocked in backoff | Check `ContainerPausingBackOffHandler`, `max.poll.interval.ms`, and poll timeout |
| Listener-level handler does not retry | Handler does not rethrow the exception | Propagate exception to container-level handler |

## 37. Safe migration workflow

1. Record the current Spring Boot, Spring Kafka, and Kafka client versions.
2. Find all legacy handlers, factory setters, and listener-level handlers.
3. List current retry counts, backoffs, exception classifications, recoverers, DLT, and AckMode.
4. Choose `DefaultErrorHandler` or the corresponding common handler.
5. Migrate custom handlers to the target version's exact API.
6. Wire the handler into the right factory or auto-configured bean.
7. Check transactions and `AfterRollbackProcessor`.
8. Run integration tests for record, batch, DLT, offsets, and recovery failures.
9. Canary deploy with metrics for retries, DLT, consumer lag, and container state.
10. Remove legacy dependencies/APIs only after confirming all listeners use common handlers.

## 38. Pre-completion upgrade checklist

- Identified the exact Spring Kafka version resolved by dependency management.
- No custom code depends on deprecated legacy APIs without a migration plan.
- Record and batch listeners have appropriate handlers.
- Retry count is understood as additional retries after the initial delivery.
- `handleOtherException` handles consumer/poll errors without a record.
- Custom handlers use the right API version: 2.8 vs. 2.9+.
- Seek behavior and `seekAfterError` have been verified.
- Offset commits, `ackAfterHandle`, and `commitRecovered` match intent.
- DLT has sufficient partitions, serializers, and ACLs.
- Recovery failures do not lose records.
- Transaction rollback still works when a listener throws an exception.
- Listener-level error handlers do not accidentally swallow exceptions needing retry.
- Batch listeners identify failed records via `BatchListenerFailedException` when needed.
- Retry topics are used only when non-blocking semantics and corresponding ordering are acceptable.
- Integration tests verify redelivery, offsets, DLT, and rebalances.
- Metrics/logs exist for failed delivery, recovered, recovery failed, and DLT publish failures.

The most important change is moving from two separate record/batch handler families to `CommonErrorHandler` starting in 2.8, and then updating the custom handler API from `handleRecord`/`remainingRecords` to `handleOne`/`seeksAfterHandling` starting in 2.9. During upgrades, preserve retry, seek, offset commit, batch, and transaction semantics with integration tests; only change classes or methods after confirming the exact behavior the legacy code performs.

## References

- [Spring Kafka – Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka 2.8 – CommonErrorHandler API](https://docs.spring.io/spring-kafka/docs/2.8.x/api/org/springframework/kafka/listener/CommonErrorHandler.html)
- [Spring Kafka 2.9 – DefaultErrorHandler API](https://docs.spring.io/spring-kafka/docs/2.9.5/api/org/springframework/kafka/listener/DefaultErrorHandler.html)
- [Spring Kafka 3.0 – CommonErrorHandler API](https://docs.spring.io/spring-kafka/docs/3.0.x/api/org/springframework/kafka/listener/CommonErrorHandler.html)
- [Spring Kafka – Change History](https://docs.spring.io/spring-kafka/reference/appendix/change-history.html)

# Performing Recovery After Retry Attempts

Retries give a listener another chance to process a record when an error might be transient. However, retry attempts must be bounded. Once `BackOff` exhausts its attempts or an exception is classified as non-retryable, Spring Kafka moves to the recovery step to decide how to handle the failed record. A common choice is sending the record to a dead-letter topic (DLT) for later investigation and replay.

Recovery is the final step of an error-handling cycle on the consumer side. You must clearly configure where the record is moved, how to verify the move succeeded, and when the offset is allowed to advance.

## 1. When Is the Recoverer Called?

In Spring Kafka 2.8 and later, `DefaultErrorHandler` uses `BackOff` to coordinate retries. When a listener throws an exception, the handler checks the exception type and backoff state:

- If the exception is retryable and attempts remain, the handler waits per backoff and redelivers the record to the listener.
- If the exception is non-retryable, the handler skips remaining attempts and invokes the recoverer.
- Once retry attempts are exhausted, the handler calls the recoverer to handle the failed record.

The recoverer receives the `ConsumerRecord` together with the exception that caused the listener to fail. For record listeners, this contract is represented by `ConsumerRecordRecoverer`. A recoverer can log, store failure details in another system, skip the record under an approved policy, or publish the record to a DLT.

```java
public interface ConsumerRecordRecoverer {
    void accept(ConsumerRecord<?, ?> record, Exception exception);
}
```

If the recoverer returns normally, the error handler considers the record recovered. If the recoverer throws an exception, recovery has not completed; the record can continue through the container's error-handling mechanism. Therefore, the recoverer must return normally only after the required recovery action has completed.

## 2. Routing Failed Records to a DLT with DeadLetterPublishingRecoverer

`DeadLetterPublishingRecoverer` is Spring Kafka's built-in recoverer. It uses `KafkaTemplate` to publish failed records to another topic, typically suffixed with `.DLT`.

```java
@Bean
public DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {
    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(dltTemplate);

    // Treat DLT send failures as recovery errors so the container does not silently skip them.
    recoverer.setFailIfSendResultIsError(true);

    DefaultErrorHandler handler = new DefaultErrorHandler(
        recoverer, new FixedBackOff(1_000L, 2L));
    handler.addNotRetryableExceptions(InvalidOrderException.class);
    return handler;
}
```

With the default destination resolver, records from the `orders` topic are sent to `orders.DLT` with the partition matching the source partition. Consequently, if the source topic has multiple partitions, the DLT needs enough partitions to accept records routed this way.

`FixedBackOff(1_000L, 2L)` permits two retries after the initial attempt. When all three attempts fail, the recoverer publishes the record to the DLT. `InvalidOrderException` is marked non-retryable, so records hitting this error proceed directly to recovery.

## 3. Customizing the Target Topic for Failed Records

In practice, you may want DLTs split by event type, tenant, or error category. `DeadLetterPublishingRecoverer` accepts a destination resolver to select the target topic and partition:

```java
DeadLetterPublishingRecoverer recoverer =
    new DeadLetterPublishingRecoverer(
        dltTemplate,
        (record, exception) -> {
            String dltTopic = record.topic() + ".DLT";
            return new TopicPartition(dltTopic, record.partition());
        });
```

The resolver can inspect the source topic, partition, key, or exception type. Ensure the target topic exists and the chosen partition is valid. If routing to the same source partition number, the DLT needs at least as many partitions; if consolidating into a single partition, evaluate load and processing order.

Do not generate target topics arbitrarily from exception message content. Topic names should follow stable, managed conventions with clear retention policies so failed data is not retained indefinitely.

## 4. Ensuring DLT Publishing Is Confirmed

A critical failure scenario occurs when the listener fails and the DLT send itself also fails—for example, the broker is unavailable, the target topic does not exist, or the producer encounters a serialization error. If the handler marks recovery as successful while the record was never persisted in the DLT, the consumer can commit the offset and lose the ability to reprocess the record.

With `DeadLetterPublishingRecoverer`, `setFailIfSendResultIsError(true)` instructs the recoverer to treat send-result failures as recovery errors and throw an exception accordingly. This lets the error handler know publishing did not succeed. Verify the API for your Spring Kafka version and configure a send-result wait timeout suited to your environment.

The `KafkaTemplate` producer must have serializers compatible with keys and values. This is especially important for deserialization failures: a record may hold raw byte arrays or a value not converted into the expected domain type. The application must configure the template to send every failed data representation that the recovery path can actually receive.

`DeadLetterPublishingRecoverer` adds headers containing source details, typically topic, partition, offset, and exception. When consuming the DLT, use these headers to identify the original record and failure cause. Do not rely solely on exception text in logs, as records need to be traceable even after logs expire.

## 5. How Does the Offset Advance After Recovery?

Kafka tracks offsets per partition. When the recoverer completes and the error handler returns normally, `DefaultErrorHandler` by default allows the container to acknowledge progress after error handling via `ackAfterHandle` (default `true`). Actual offset commits follow the container's `AckMode` and commit mechanism.

There is a `commitRecovered` option for the handler to commit the recovered record's offset itself; this option requires `AckMode.MANUAL_IMMEDIATE`. Enable it only when the application intentionally uses manual acknowledgements and the offset commit responsibility is clearly defined.

If the recoverer throws an exception because DLT sending failed, recovery has not completed. The record is not treated as handled; the error handler continues applying its configured error-handling mechanism. That is why DLT send results must be verified before allowing the offset to advance.

## 6. Writing a Custom Recoverer for Business Needs

Not every system needs a DLT. Some applications prefer saving failed records into an audit table or signaling a separate operational workflow. You can implement `ConsumerRecordRecoverer` with a lambda or dedicated class:

```java
@Bean
public DefaultErrorHandler kafkaErrorHandler(FailureAuditService auditService) {
    ConsumerRecordRecoverer recoverer = (record, exception) -> {
        auditService.saveFailure(
            record.topic(),
            record.partition(),
            record.offset(),
            record.key(),
            record.value(),
            exception.getClass().getName(),
            exception.getMessage());
    };

    return new DefaultErrorHandler(
        recoverer, new FixedBackOff(1_000L, 2L));
}
```

This example returns only after `saveFailure` finishes. If saving the audit record fails, the service should throw a runtime exception so recovery is treated as failed. When writing to a database, use an idempotency key based on topic, partition, offset, or event ID: the application may reprocess the record if the process crashes after saving the audit record but before Kafka commits the offset.

If policy dictates skipping a particular record category, express it explicitly via a recoverer with logging and metrics, recording necessary metadata. An empty recoverer or one that catches and ignores exceptions can silently drop business data without anyone noticing.

## 7. Handling Batch Listeners

For batch listeners, recovery depends on how the listener reports the failing record's position. Throwing `BatchListenerFailedException` with a valid index allows `DefaultErrorHandler` to handle records before the failure and focus retry/recovery on the failed record and remaining items per batch semantics. If the listener throws an exception without identifying a record, the handler may fall back to retrying or recovering the entire batch.

If a batch listener needs to move a single specific record to a DLT, provide the exact index in `BatchListenerFailedException` and test records before, at, and after the failing record. Do not infer the index from the Kafka offset: the index is the position in the batch list, whereas the offset belongs to the partition.

## 8. Replaying Records from the DLT

A DLT isolates records needing investigation; it does not automatically fix data or return records to the main stream. A replay procedure should follow these steps:

1. Read source metadata from DLT headers to identify the original topic, partition, offset, and exception.
2. Analyze the root cause, fix the data, or deploy a code fix before replaying.
3. Send the record back to the target topic or a controlled replay stream, preserving the event ID for tracing.
4. Record replay outcomes and cap replay attempts; if it fails again, the record re-enters the recovery flow.

Replay consumers must be idempotent because a record can be resent or reprocessed if offsets were not committed. If a record produces database side effects, enforce an event ID with a unique constraint or store a processing marker within the same data transaction.

## 9. Testing Recovery and Failure Scenarios

An integration test should produce a record that causes the listener to fail repeatedly, verify the retry count, and confirm the record lands in the DLT with the right key, payload, and source headers. Next, test a non-retryable exception to confirm recovery occurs immediately after the first attempt.

Additional test cases to include:

- The DLT topic does not exist or the producer cannot send the record.
- The serializer cannot handle the actual key/value types.
- A custom recoverer throws an exception while saving the audit entry.
- The application stops after recovery completes but before the offset is committed.
- A record is replayed multiple times while business logic produces no duplicate side effects.

Use Embedded Kafka or Testcontainers to verify broker, consumer, and offset behavior. You can use Awaitility to wait for records to appear in the DLT instead of fixed sleeps. Tests should verify that a failed recovery does not advance the offset as if the record had been processed.

## 10. Operational Monitoring

Track the number of records sent to the DLT by source topic, exception type, DLT publish failure rate, age of the oldest record in the DLT, and replay counts. Alert on sudden DLT spikes or sustained recovery publish failures. Set retention long enough for investigation, while also establishing a cleanup process once retention expires.

Recovery completes only when the chosen action is confirmed successful: publishing to the DLT, saving an audit record, or an intentional skip decision. Combining a reliable recoverer, send-result confirmation, timely offset commits, and an idempotent replay workflow enables Spring Kafka streams to handle failed records while preserving traceability and recoverability.

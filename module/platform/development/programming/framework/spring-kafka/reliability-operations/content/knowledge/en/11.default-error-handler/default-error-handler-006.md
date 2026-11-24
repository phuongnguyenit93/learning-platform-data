# seekAfterError=false

In Spring Kafka, `DefaultErrorHandler` normally handles errors by moving the consumer's read position back to the failed record so that it and any unprocessed records are re-read on the next poll. This approach uses Kafka consumer seek to change the partition's read position.

Since Spring Kafka 2.9, you can configure `seekAfterError=false` so the container retains unprocessed records in memory and resubmits them to the listener after the error handler completes. Instead of seeking the partition for Kafka to re-fetch those records, the container temporarily pauses the consumer, performs a poll to maintain consumer group membership/heartbeats, and then resubmits the retained records.

This option changes **how the container returns unprocessed records to the listener**. It does not replace retry policies, exception classification, recoverers, acknowledgment modes, or offset commit rules. Those aspects still must be designed separately.

## 1. Default Behavior: Seek After Error

Suppose a poll fetches four records from partition `orders-0`:

| Offset | Outcome |
|---:|---|
| 100 | Listener processes successfully |
| 101 | Listener throws an exception |
| 102 | Unprocessed |
| 103 | Unprocessed |

With the default seek mechanism, the error handler processes the failing record according to retry/backoff. The relevant partitions are seeked back to the position that needs re-reading so the consumer can re-fetch the failed record or remaining unprocessed records on the next poll.

```text
Poll: 100, 101, 102, 103
       |
       +--> 100 processed successfully
       |
       +--> 101 error
                |
                v
          DefaultErrorHandler
                |
                v
          retry / recover
                |
                v
          seek partition to offset to re-read
                |
                v
          next poll fetches unprocessed records
```

Seek changes the Kafka consumer's read position. Records needing reprocessing are fetched from the broker on the next poll. This is the traditional `DefaultErrorHandler` mechanism and is generally suitable for standard record-processing flows.

## 2. Behavior When `seekAfterError=false`

When `seekAfterError=false` is set, the container does not use seek to bring back unprocessed records. The container keeps those records in memory and resubmits them to the listener after the error handler finishes.

```text
Poll: 100, 101, 102, 103
       |
       +--> 100 processed successfully
       |
       +--> 101 error
                |
                v
          DefaultErrorHandler
                |
                v
          retry / recover
                |
                v
          container retains unprocessed records
                |
                v
          pause consumer
                |
                v
          poll once to maintain group membership
                |
                v
          resubmit retained records to listener
```

Polling while the consumer is paused is an important part of the mechanism. It keeps the consumer participating in the group and sending heartbeats while the container holds records for reprocessing. Afterward, the container delivers the retained records back to the listener without requiring the broker to re-send all of them via a new fetch.

In the example above, record 100 already finished and does not need reprocessing. Record 101 is retried or recovered according to the error handler's decision; unprocessed records 102 and 103 are retained to continue once the handler completes. Exactly which records are retained depends on listener type, failure position, and recovery outcome.

## 3. Configuration in DefaultErrorHandler

`seekAfterError` is a property of `DefaultErrorHandler`. Its default value is `true`, so an application only needs to set `false` when it wants the retain-and-resubmit mode.

Configuration example:

```java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);
    recoverer.setFailIfSendResultIsError(true);

    DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L));

    handler.setSeekAfterError(false);
    return handler;
}
```

In this example, the listener gets an initial delivery and up to two retries, one second apart. When retries are exhausted, the recoverer sends the record to the DLT. `setFailIfSendResultIsError(true)` surfaces DLT publish failures in Spring Kafka versions supporting this API. Ensure the DLT exists, has sufficient partitions, uses compatible serializers, and that the producer has write permissions.

Attach the handler to the listener container factory:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
orderKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        DefaultErrorHandler kafkaErrorHandler) {

    ConcurrentKafkaListenerContainerFactory<String, OrderCreated> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.RECORD);

    return factory;
}
```

Listener using this factory:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "orderKafkaListenerContainerFactory")
public void consume(OrderCreated event) {
    orderService.processIdempotently(event);
}
```

This is an illustrative configuration for a record listener. Bean names, generic types, serializers, and error handlers must match your application structure. If the application has multiple listener container factories, only listeners using the factory configured with this handler are affected by `seekAfterError=false`.

## 4. `seekAfterError=false` Does Not Change the Retry Policy

Two decisions must stay separated:

- **Retry policy:** which exceptions are retried, how many times, and how long to wait.
- **Redelivery mechanism:** after the error handler handles an error, whether the container seeks/re-fetches or retains/resubmits unprocessed records.

`seekAfterError=false` only changes the second decision. For example:

```java
DefaultErrorHandler handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(2_000L, 3L));

handler.addNotRetryableExceptions(
        InvalidOrderException.class,
        UnsupportedEventVersionException.class);

handler.setSeekAfterError(false);
```

In this configuration:

- `InvalidOrderException` and `UnsupportedEventVersionException` are classified as non-retryable, so they go straight to the recoverer.
- Retryable exceptions use `FixedBackOff` with at most three retries after the initial delivery.
- After the error handler finishes, the container retains/resubmits unprocessed records rather than seeking the partition to re-fetch.

Do not increase retry counts merely because you switched to `seekAfterError=false`. If data errors cannot be fixed by retrying, classify them as non-retryable. If dependency errors can recover, use bounded backoff and cap total duration.

## 5. Relationship to Committed Offsets and Acknowledgment Mode

`seekAfterError=false` does not commit offsets by itself. The container still commits according to acknowledgment mode, listener processing status, and error handler configuration.

With `AckMode.RECORD`, the container commits after each record is processed successfully per listener container rules. With `AckMode.BATCH`, the container commits per batch after records in the batch succeed. With manual acknowledgment, the listener must call `acknowledge()` once the required work is complete.

If the recoverer handles a failed record successfully, committing the recovered record is a separate decision. For example, `DefaultErrorHandler.setCommitRecovered(true)` instructs the container to commit the offset of a recovered record and requires `AckMode.MANUAL_IMMEDIATE`. Simply setting `seekAfterError=false` does not replace that setting.

Manual acknowledgment example:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "manualOrderKafkaListenerContainerFactory")
public void consume(
        OrderCreated event,
        Acknowledgment acknowledgment) {

    orderService.processIdempotently(event);
    acknowledgment.acknowledge();
}
```

The listener acknowledges only after business side effects complete. If the process stops after side effects succeed but before committing the offset, the record may be redelivered upon restart. Therefore, `processIdempotently()` must perform deduplication or ensure the same event never creates duplicate side effects.

Do not treat `seekAfterError=false` as an exactly-once mechanism. It does not make offset commits and database transactions atomic. For external side effects outside Kafka, inbox/outbox or idempotency is still required.

## 6. Behavior When the Recoverer Succeeds or Fails

Once retries are exhausted, the recoverer can perform an alternative action such as sending the record to a DLT. The recovery outcome determines how the container proceeds with the retained records.

### 6.1. Recovery Succeeds

When the recoverer finishes successfully, the error handler can treat the failed record as handled per the recovery policy. The container continues with the remaining unprocessed records. If committing the recovered offset is needed, configure `commitRecovered` and the appropriate acknowledgment mode.

```text
Failed record
   |
   v
Retries exhausted
   |
   v
DLT publish succeeds
   |
   v
Recovery complete
   |
   v
Container continues unprocessed records
```

### 6.2. Recovery Fails

If DLT publishing fails, the recoverer must report the error rather than letting the handler treat the record as recovered. In that case, the offset must not be committed as if the record finished processing; inspect retry state, backoff, and error-handling behavior in your Spring Kafka version.

With `DeadLetterPublishingRecoverer`, you can use `setFailIfSendResultIsError(true)` in supported versions so send-result errors surface as recovery failures. At the same time, monitor timeouts, ACLs, topics, partitions, and DLT serializers.

Do not let a DLT outage create an uncontrolled infinite retry loop. Bound backoff, alert on recovery failures, and have a plan to throttle or pause consumers when the DLT destination is unavailable.

## 7. Record Listener and Batch Listener

### 7.1. Record Listener

With a record listener, each listener invocation processes one record. When a record fails, `DefaultErrorHandler` can retry that record or invoke the recoverer. Unprocessed records from the poll are retained by the container when `seekAfterError=false` and resubmitted after the error handler completes.

Record listeners fit when each event has an independent processing boundary, exceptions can be classified per record, and offset commits need to track per-event progress closely.

### 7.2. Batch Listener

A batch listener receives multiple records in one invocation. If a record in the batch fails, the error handler needs to know the error position to tell which part was processed and which part needs retry/recovery. Spring Kafka supports `BatchListenerFailedException` so the listener can indicate the failing index or record.

```java
@KafkaListener(topics = "orders", groupId = "batch-order-service")
public void consume(List<ConsumerRecord<String, OrderCreated>> records) {
    for (int i = 0; i < records.size(); i++) {
        try {
            orderService.processIdempotently(records.get(i).value());
        }
        catch (InvalidOrderException ex) {
            throw new BatchListenerFailedException(
                    "Invalid order at batch index " + i, ex, i);
        }
    }
}
```

When the exception identifies the failing record, the error handler can process the preceding slice, retry or recover the failed record, and continue with the rest according to batch semantics. If the listener throws a generic exception without specifying the failing position, the handler may have to retry the whole batch. In that case, records that already produced side effects before the failure may be reprocessed; idempotency is required.

`seekAfterError=false` changes how the container retains/resubmits unprocessed records, but does not eliminate the requirement to pinpoint failed records in batches. Test batch listeners specifically with realistic record counts, batch indices, commit modes, and the error handler.

## 8. Benefits and Costs of Non-Seek Mode

| Aspect | `seekAfterError=true` | `seekAfterError=false` |
|---|---|---|
| How unprocessed records return | Seek partition and re-fetch on next poll | Container retains records and resubmits |
| Data reused | Broker re-sends via fetch | Already-polled records held in memory |
| Consumer while waiting | Follows pause/backoff behavior of error handler and container | Container pauses and polls once to keep group membership before resubmitting |
| Memory impact | Does not need to retain all remaining records for resubmission this way | Must hold unprocessed records in memory |
| Retry/backoff | Decided by error handler | Still decided by error handler |
| Offset commit | Per ack mode and recovery config | Does not change commit principles |

Non-seek mode avoids re-fetching records already in memory and lets the container manage continuation without altering the partition read position. In return, the container must hold unprocessed records until resubmission finishes.

With large payloads, large batches, or many partitions, retained data can be substantial. Factor in `max.poll.records`, record sizes, fetch limits, concurrency, and application heap. Do not raise `max.poll.records` purely for throughput if listeners could retain many records in memory during long retries.

## 9. Polling, Pausing, and Group Membership

When the container holds records for resubmission, the consumer must continue maintaining group membership. If a consumer fails to poll for too long, the coordinator may consider it gone and trigger a rebalance. Therefore, the container pauses the consumer and executes a poll to preserve heartbeats/group membership before resubmitting records.

Pausing here does not mean the consumer is closed or leaves the group. The container still manages the consumer and polls internally as needed. This is especially important when backoffs are long or records are held while the handler executes.

However, the application still must configure reasonable processing and backoff durations. `max.poll.interval.ms`, `session.timeout.ms`, heartbeats, and batch processing times still govern group stability. Verify behavior for your Kafka client and Spring Kafka versions, especially when customizing polling, pause/resume, or using async listeners.

## 10. When Should You Use `seekAfterError=false`?

This mode is worth considering when:

- You want the container to keep already-polled records for redelivery without seeking partitions.
- You want to avoid re-fetching unprocessed records in flows where batches or payloads are better kept in memory.
- You clearly understand the heap impact of holding records and have appropriate poll limits.
- You use `DefaultErrorHandler` and want explicit container-level resubmission semantics.
- You have tests proving retries, recovery, commits, and rebalances still behave properly with your real listener.

Keeping the default seek behavior is usually simpler if the application has no specific need to change it. Do not turn on this mode simply because the setting sounds more optimal; actual benefits depend on batch sizes, payloads, backoff times, and consumer load.

## 11. Common Operational Issues

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Unprocessed records do not return to listener | Handler/recoverer marked record as recovered or container factory is not using the intended handler | Check exception classification, recoverer, and factory name on listener |
| Records processed repeatedly | Side effect completed before offset commit; record resubmitted or replayed after restart | Make handler idempotent and inspect acknowledgment/commit mode |
| Consumer lag grows during long retries | Long backoff, low processing throughput, or downstream still failing | Cap retries, tune backoff, and monitor oldest record age |
| Heap grows during error periods | Container holds many unprocessed records; large poll batch/payloads | Reduce `max.poll.records`, limit payload/batch size, and monitor heap/GC |
| Group rebalances while handling errors | Consumer fails to poll in time, processing/backoff exceeds limits, or network/heartbeat issues | Check `max.poll.interval.ms`, session timeout, and poll behavior |
| DLT publish fails yet flow advances | Recoverer does not surface send failures | Enable send-result checks, monitor publish errors, and verify offsets |
| Batch reprocessed multiple times | Listener does not identify failed record or prior side effects are not idempotent | Use `BatchListenerFailedException` with correct index and design batch recovery |
| Config change has no effect | Listener uses a different container factory | Check `containerFactory` on `@KafkaListener` and actual wired beans |

When investigating, always verify the exact cluster, topic, partition, group ID, and listener container. Inspect error handler logs alongside committed offsets, lag, rebalances, and DLT status. Never manually reset offsets to hide resubmission or recovery bugs; resetting backward can cause duplicates, while resetting forward can skip data.

## 12. Testing `seekAfterError=false`

An integration test should verify how the container handles records before, at, and after the error position. You can use a Kafka test broker or test environment.

Recommended scenarios:

1. Create a topic with at least one partition and a fresh consumer group.
2. Send records with identifiable IDs and offsets.
3. Configure the listener to fail deterministically on a specific record, such as the second record.
4. Enable `DefaultErrorHandler.setSeekAfterError(false)` with a short backoff for testing.
5. Verify listener invocation counts match the retry policy.
6. Verify the failing record is recovered or retried per classification.
7. Verify unprocessed records are resubmitted without any being dropped.
8. Verify the committed offset advances only according to configured acknowledgment/recovery rules.
9. Simulate a DLT publish failure and verify the record is not treated as successfully recovered.
10. Stop/restart the consumer mid-processing to verify uncommitted records are redelivered from durable offsets.

To distinguish seek from resubmit, observe consumer/handler logs, fetch counts if metrics support them, and the sequence of records received by the listener. Do not rely solely on total listener invocation count since retries, redeliveries, and restarts all increase that number.

## 13. Production Rollout Principles

Before enabling `seekAfterError=false`, confirm:

1. Your Spring Kafka version supports this mode; the feature arrived in Spring Kafka 2.9.
2. The target listener actually uses the `DefaultErrorHandler` configured with `setSeekAfterError(false)`.
3. Retry/backoff and exception classification fit each error type.
4. The recoverer persists records durably; DLT publish failures surface as recovery errors.
5. Ack mode and `commitRecovered` are configured independently and not confused with the resubmission mechanism.
6. Batch listeners identify failing records accurately and have idempotent side effects.
7. `max.poll.records`, payload sizes, concurrency, and heap are sufficient to retain records during error handling.
8. `max.poll.interval.ms`, session timeout, and heartbeats match processing/backoff durations.
9. Dashboards cover consumer lag, retry rate, DLT rate, rebalances, processing latency, and heap/GC.
10. Recovery success, recovery failure, restarts, rebalances, and batch listeners are tested before rollout.

`seekAfterError=false` allows Spring Kafka to retain unprocessed records and resubmit them after the error handler completes. This mechanism changes how redelivery takes place inside the container, while retry policy and offset commits retain their own separate responsibilities. When choosing this mode, manage memory, poll intervals, group membership, and idempotency to keep the consumer stream safe during errors.

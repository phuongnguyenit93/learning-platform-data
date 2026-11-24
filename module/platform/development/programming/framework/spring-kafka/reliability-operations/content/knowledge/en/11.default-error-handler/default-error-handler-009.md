# Batch Listener Retries

In Spring Kafka, a **batch listener** receives a group of records in a single invocation rather than one record at a time. This reduces overhead when processing many messages, but raises an important question when an error occurs: which record in the batch failed, and how far were the remaining records processed?

**DefaultErrorHandler** supports retries for batch listeners. If the listener throws a regular exception, the framework does not know exactly which record caused the error and therefore usually has to retry the entire batch. If the listener can pinpoint the failed record, it can throw **BatchListenerFailedException** with the record's position so the handler commits the preceding portion and retries from the failed record onward.

Choosing the right strategy reduces duplicate processing, prevents a single failing record from blocking the whole batch for too long, and keeps offsets consistent. You need to understand batch retries, backoff, exception classification, recovery/DLT, and how batch listeners differ from record listeners.

## 1. How Does a Batch Listener Work?

With a record listener, the container invokes the listener once per record. With a batch listener, the container takes the records from a poll and passes the entire group to a single listener invocation.

Record listener example:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-service"
)
public void handle(OrderCreated event) {
    orderService.process(event);
}
~~~

Batch listener example:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-service"
)
public void handle(List<OrderCreated> events) {
    orderService.processBatch(events);
}
~~~

Batch listeners fit cases where multiple records can be processed together, such as bulk inserts, batch updates, or coalescing I/O operations. They also reduce listener invocation overhead and can improve throughput.

However, a single listener invocation can represent multiple records and multiple offsets. If the listener processes nine records and fails on the tenth, the container needs to know whether the preceding nine completed in order to decide commits and retries.

### 1.1 Enabling a Batch Listener

When configuring ConcurrentKafkaListenerContainerFactory manually, enable batch mode:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
ordersBatchListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        CommonErrorHandler errorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setCommonErrorHandler(errorHandler);

    return factory;
}
~~~

Listener using the factory:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-service",
    containerFactory = "ordersBatchListenerFactory"
)
public void handle(List<OrderCreated> events) {
    orderService.processBatch(events);
}
~~~

If using Spring Boot auto-configuration, batch listeners can be enabled via the property matching your Spring Boot/Spring Kafka version. When using a custom factory, the setting must be placed on the exact factory referenced by the listener.

### 1.2 Where Does Batch Size Come From?

A batch listener typically receives the records returned by a single poll. Actual batch size is influenced by:

- **max.poll.records**: caps the number of records a consumer returns in one poll.
- Amount of records currently available on assigned partitions.
- Record sizes and fetch limits.
- Time elapsed between polls.
- The consumer's partition assignment.

Example:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        max.poll.records: 200
~~~

The value 200 is the upper bound on records returned in one consumer poll; actual batches can be smaller. With a concurrent container, each child consumer performs its own polls, so each child may receive differently sized batches.

Do not increase max.poll.records without measuring processing duration. Overly large batches can slow down the listener, increase memory usage, lengthen retry cycles, and make pinpointing failed records harder.

## 2. How Does DefaultErrorHandler Handle Batch Errors?

**DefaultErrorHandler** is Spring Kafka's common error handler. It can handle exceptions from both record listeners and batch listeners, though how retry scope is determined differs.

For a record listener, the container knows which record was being processed when the exception occurred. For a batch listener, given only a regular exception, the container does not know which specific record in the batch failed.

As a result, there are two main paths:

1. **Failed record unknown**: the handler uses fallback batch retry and retries the entire batch.
2. **Failed record identified**: the listener throws BatchListenerFailedException with the failing index or record so the handler handles the preceding slice and the remainder separately.

~~~mermaid
flowchart TD
    A["Batch listener receives batch"] --> B["Listener processes records"]
    B --> C{"Exception thrown?"}
    C -->|No| D["Container handles commit per AckMode"]
    C -->|Yes| E{"BatchListenerFailedException?"}
    E -->|No| F["Fallback batch retry"]
    F --> G["Retry entire batch per BackOff"]
    G --> H{"Retries exhausted?"}
    H -->|No| B
    H -->|Yes| I["Recovery per handler config"]
    E -->|Yes| J["Identify failed index/record"]
    J --> K["Commit portion before failed record"]
    K --> L["Retry failed record and remainder"]
    L --> M{"Retry succeeded?"}
    M -->|Yes| N["Continue processing batch"]
    M -->|No| O["Recover failed record per policy"]
~~~

The diagram illustrates the two strategies conceptually. Exact details of seeking, retaining batches in memory, committing, and recovery depend on container configuration and Spring Kafka version.

## 3. Retrying the Entire Batch When the Failed Record Is Unknown

If a batch listener throws a standard exception such as **RuntimeException**, the handler does not know which record caused the error. With the fallback batch handler, Spring Kafka retries the entire batch according to BackOff.

Example batch of five records:

| Position | Record | Initial Outcome |
|---:|---|---|
| 0 | order-101 | Processed successfully |
| 1 | order-102 | Processed successfully |
| 2 | order-103 | Processed successfully |
| 3 | order-104 | Throws exception |
| 4 | order-105 | Unprocessed |

If the listener simply throws **RuntimeException**, the handler does not know record 3 is the culprit. The entire batch may be retried, including order-101, order-102, and order-103 which already succeeded on the prior call.

### 3.1 Impact of Whole-Batch Retries

Advantages:

- The listener does not need to determine an error index.
- Fits errors affecting the whole batch, such as an unavailable database or downstream service timeout.
- Keeps batch-processing logic simple when operations only succeed or fail at the group level.

Limitations:

- Successfully processed records may be reprocessed.
- Large batches incur high retry cost.
- One poison record can cause the entire batch to fail repeatedly.
- Side effects may duplicate if the listener is not idempotent.
- Batch recovery latency depends on the slowest or failing record.

If a batch listener writes to the database record-by-record before moving to the next, a mid-batch exception can happen after partial side effects were committed. Whole-batch retry will re-run the already-completed portion. Use an appropriate database transaction or idempotency keys to handle this safely.

### 3.2 FallbackBatchErrorHandler and In-Memory Retry

On the fallback batch retry path, Spring Kafka can retain the batch to be retried in memory and temporarily pause the consumer while running BackOff. The container continues polling as needed to keep the consumer alive in the group, then re-invokes the listener with that batch.

This differs from simply seeking the whole partition and waiting for a new poll to assemble a different batch. The goal is to retry the exact batch that failed when the culprit record could not be identified.

Because the batch is held for retry, keep in mind:

- The batch occupies memory throughout the retry period.
- Long backoffs extend batch processing duration.
- The consumer must maintain lifecycle and poll mechanics per the container.
- Partitions owned by the consumer may be affected while the batch is retrying.
- Whole-batch retries can repeat side effects executed prior to the exception.

Exact fallback behavior can vary across versions. Confirm how the handler is configured and test on your deployed version.

## 4. Identifying the Failed Record with BatchListenerFailedException

If the listener knows exactly which record failed, throw **BatchListenerFailedException** with the corresponding index or record. This allows DefaultErrorHandler to process the batch along record boundaries.

Example batch listener receiving a list of ConsumerRecord:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-service",
    containerFactory = "ordersBatchListenerFactory"
)
public void handle(List<ConsumerRecord<String, OrderCreated>> records) {
    for (int index = 0; index < records.size(); index++) {
        ConsumerRecord<String, OrderCreated> record = records.get(index);

        try {
            orderService.process(record.value());
        }
        catch (Exception ex) {
            throw new BatchListenerFailedException(
                "Failed to process order at batch index " + index,
                ex,
                index
            );
        }
    }
}
~~~

The example uses the constructor with message, cause, and index; verify the constructor matching your project's Spring Kafka version.

When the handler receives BatchListenerFailedException, it knows the failed record's position in the batch:

- Records before the failed index can be committed per batch error-handling mechanics.
- The failed record and records after it are reprocessed.
- If retries for the failed record exhaust allowed attempts, the recoverer can handle that record per policy.
- Once the failed record is recovered successfully, the remainder of the batch can continue.

This avoids re-running records already confirmed complete before the failing record.

### 4.1 Choosing the Exact Index

The index must match the record's position in the batch list received by the listener. Never use the Kafka offset as the index. An offset is a position in a partition, whereas index is the element position in the list.

Example:

| Index in Batch | Topic-Partition | Offset |
|---:|---|---:|
| 0 | orders-0 | 501 |
| 1 | orders-1 | 207 |
| 2 | orders-0 | 502 |
| 3 | orders-2 | 91 |

Index 2 does not mean offset 2. If the failing record is the third element, the index passed into the exception is 2.

If the listener filters, sorts, or transforms the batch into another list before processing, preserve a mapping back to the original batch. If the index is wrong, the handler may commit the wrong slice or retry the wrong range.

### 4.2 Identifying the Record by ConsumerRecord

Where supported by your Spring Kafka version, BatchListenerFailedException can take the failed ConsumerRecord instead of an index. This is useful when the listener works with record metadata and wants to avoid confusing a transformed index with the original batch.

Whether using an index or a record, the listener must supply a record that actually belongs to the current batch. If the failing record cannot be determined with certainty, falling back to whole-batch retry is safer than guessing an index.

## 5. Processing Flow When the Failed Record Is Identified

Suppose a batch has records in this order:

| Index | Record | Outcome |
|---:|---|---|
| 0 | A | Success |
| 1 | B | Success |
| 2 | C | Failure |
| 3 | D | Unprocessed |
| 4 | E | Unprocessed |

The listener throws BatchListenerFailedException with index 2.

In principle, DefaultErrorHandler can:

1. Commit offsets for the successfully processed records before C.
2. Retry starting from record C and subsequent records.
3. If C succeeds, continue with D and E.
4. If C keeps failing until BackOff is exhausted, invoke the configured recoverer.
5. If recovery succeeds, commit the corresponding position and continue processing the remainder per container flow.

Records before the error do not need to be re-run when the handler receives the correct failed index and commits successfully. However, if the batch spans multiple partitions, offset commits occur per topic-partition and follow each partition's offset order. Do not interpret an index as a global offset.

### 5.1 Why Are Subsequent Records Also Retried?

The listener processes a batch from a single poll. When record C fails, D and E have not yet been confirmed complete. The container must ensure those records still get processed after C is retried or recovered.

If you simply skipped C and committed all subsequent offsets, the application could lose processing for D and E. Therefore, the slice from the failing record onward must be handled in an order consistent with offsets and partitions.

### 5.2 When the Failed Record Is Recovered

After retries are exhausted, the recoverer can send the failed record to a DLT or perform another recovery action. If recovery completes per policy, the handler can treat the failed record as handled and proceed to commit the corresponding offset.

If the recoverer throws an exception or DLT publishing fails, do not treat the record as recovered. The handler must preserve reprocessability per offset semantics to avoid dropping records.

Monitor recoverer logs and metrics, especially when the DLT broker/topic is unavailable. Recovery failure is a separate operational incident.

## 6. Configuring DefaultErrorHandler for a Batch Listener

DefaultErrorHandler takes a recoverer and a BackOff. You can use FixedBackOff to retry at a fixed interval, or ExponentialBackOff to increase wait times between attempts.

Example:

~~~java
@Bean
DefaultErrorHandler ordersErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
            kafkaTemplate,
            (record, exception) ->
                new TopicPartition(
                    record.topic() + ".DLT",
                    record.partition()
                )
        );

    DefaultErrorHandler handler =
        new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L)
        );

    handler.addNotRetryableExceptions(
        IllegalArgumentException.class
    );

    return handler;
}
~~~

This example illustrates configuring a recoverer that sends failed records to a topic with the **.DLT** suffix while preserving the source partition number. The DLT topic must exist and have enough matching partitions; configure replication, retention, ACLs, and monitoring for the DLT.

**FixedBackOff(1_000L, 2L)** means a 1-second wait and at most 2 retries after the initial processing attempt. In total, there can be 3 listener executions for the same record on that retry path: the initial attempt and two retries.

### 6.1 Attaching the Handler to the Listener Factory

Register CommonErrorHandler on the factory used by the batch listener:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
ordersBatchListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        CommonErrorHandler ordersErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setCommonErrorHandler(ordersErrorHandler);

    return factory;
}
~~~

If multiple factories exist, attach the handler to the exact factory used by the listener. A DefaultErrorHandler bean existing in the application context does not mean every listener automatically uses it.

### 6.2 FixedBackOff and ExponentialBackOff

**FixedBackOff** keeps the wait interval constant:

~~~java
new FixedBackOff(1_000L, 3L)
~~~

This means waiting 1 second between retries, up to 3 retries.

**ExponentialBackOff** increases the wait interval exponentially:

~~~java
ExponentialBackOff backOff = new ExponentialBackOff(1_000L, 2.0);
backOff.setMaxInterval(10_000L);
backOff.setMaxElapsedTime(60_000L);
~~~

The example starts at 1 second, multiplier 2, and a maximum wait of 10 seconds. Verify actual configuration against the APIs and limits of your Spring Framework/Spring Kafka versions.

BackOff should be chosen by error type:

- Database temporarily unavailable: exponential backoff can be used.
- Rate limit: respect the retry delay requested by the downstream.
- Deterministic data errors: repeated retries rarely help.
- Broad configuration or authentication errors: stop rapid retries and fix the root cause.

## 7. Exception Classification: Retryable and Non-Retryable

Not every exception should be retried. DefaultErrorHandler provides exception classification to decide which errors can be retried and which should go straight to recovery.

Examples:

- Database or network timeouts may be transient.
- Rate limits may recover after backoff.
- Invalid payloads usually cannot fix themselves via retries.
- Mapping or validation errors may indicate bad data or code bugs.
- Authentication failures typically require fixing credentials or configuration.

You can add non-retryable exceptions:

~~~java
handler.addNotRetryableExceptions(
    IllegalArgumentException.class,
    IllegalStateException.class
);
~~~

Or add exception types that should be retried per application policy:

~~~java
handler.addRetryableExceptions(
    TransientDataAccessException.class,
    TimeoutException.class
);
~~~

These are sample classifications; do not copy exception lists blindly without understanding the root cause and recoverability of each error. Spring Kafka includes default fatal/non-retryable exception groups that can vary by version.

### 7.1 BatchListenerFailedException Is a Signal of Error Position

BatchListenerFailedException is not just a business exception. It signals to the error handler which record in the batch failed.

If the listener knows the error index, use this exception. If the listener merely throws IllegalStateException or a generic RuntimeException, the handler lacks the information to pinpoint the record and may retry the entire batch.

Never catch all exceptions and wrap them with index 0. Doing so can fool the handler into thinking the first record failed even when the error happened much later, leading to wrong commit/retry boundaries.

### 7.2 Avoiding Infinite Retries

Infinite retries can cause:

- Batches getting stuck without advancing.
- Rising partition lag.
- Consumers spending most of their time on one failing record.
- Downstreams getting hammered and overloaded.
- Subsequent records becoming blocked.
- Alerts and recovery becoming hard to control.

Choose retry counts, total retry duration, and post-exhaustion actions. If outages can last hours, consider isolating records to a DLT or using a separate reprocessing workflow.

## 8. Dead Letter Topics and Batch Recovery

A DLT is commonly used to isolate unprocessable records after retries. With batch listeners, clarify whether the handler is recovering a pinpointed record or executing fallback batch handling.

### 8.1 Recovery by Failed Record

When the listener throws BatchListenerFailedException with the right record/index, the handler knows the failed record. A recoverer such as DeadLetterPublishingRecoverer can publish that record to the DLT according to the routing strategy.

A common strategy is:

~~~text
orders-0  -> orders.DLT-0
orders-1  -> orders.DLT-1
orders-2  -> orders.DLT-2
~~~

Preserving partition numbers can be helpful for per-partition replay, but only works if the DLT has enough partitions. If the DLT has fewer partitions than the source, publishing can fail or routing will not behave as intended.

### 8.2 Recovery After Fallback Batch Retry

When there is no failed index, the handler retries the entire batch. Final recovery behavior depends on the fallback batch handler and configured recoverer. Do not assume a whole-batch exception automatically identifies which record to send to the DLT.

If you need per-record failure handling and sending the exact bad record to the DLT, the listener should identify the failed record and throw BatchListenerFailedException. If the error genuinely affects the whole batch, define an appropriate batch recovery policy and test it on your Spring Kafka version.

### 8.3 A DLT Must Be Operated Like a Main Topic

Ensure:

- Appropriate replication factor.
- Retention long enough for investigation windows.
- Dedicated ACLs for publishers and replay operators.
- Alerts when DLT volume spikes or publishing fails.
- Source metadata: topic, partition, offset, exception, and event ID.
- A runbook for fixing data, replaying, and verifying side effects.

Do not treat a record landing in the DLT as completed business work. The DLT is a quarantine zone for investigation and follow-up processing.

## 9. Batch Listeners, Acknowledgment, and Offset Commits

Batch retries tie directly to offsets. Understand when the container considers a batch complete and when it commits offsets.

### 9.1 Batch Ack Mode

For batch listeners, the container usually commits per batch: when the listener returns normally, offsets of records in the batch are committed per AckMode and container settings.

**AckMode.RECORD** does not fit a batch listener because the listener processes the entire batch in one call. With batch listeners, **BATCH** or manual acknowledgment is typically used according to application semantics.

Configuration example:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: batch
~~~

Disabling auto-commit lets the container manage offsets per ack mode. It does not automatically decide which records in the batch succeeded when the listener throws an exception. For partial batch failures, BatchListenerFailedException supplies the necessary position information.

### 9.2 Manual Acknowledgment

A batch listener can use Acknowledgment when explicit control over acknowledgment timing is needed. However, never call ack before all side effects are guaranteed complete.

Dangerous example:

1. Listener receives batch.
2. Submits work to an executor.
3. Calls ack immediately.
4. Process dies before executor completes.

The offset is committed, yet business effects may not have executed. If using manual ack or async processing, tie acknowledgment to actual completion and understand Acknowledgment thread-safety/lifecycle in your framework version.

### 9.3 Committing the Portion Before the Failed Record

When using BatchListenerFailedException, the handler can commit records prior to the failed index. Commits are performed per partition offset, not as a single index number.

If a batch contains records from multiple partitions, one partition may have multiple records and varying offsets. Understand that a committed offset represents the next position to read for each partition. Never calculate an offset as index + 1.

### 9.4 Rebalances During Retries

If retries drag on, the consumer still must meet poll/heartbeat/lifecycle requirements. Fallback batch retry has framework pause/poll mechanics to keep the consumer alive, though processing times and timeouts still must be configured properly.

If the consumer loses group membership during retries, partitions may be reassigned to another member and uncommitted records redelivered. Consequently, listeners must be idempotent even when using partial batch retries.

## 10. Database Transactions and Side Effects During Batch Retries

Batch listeners are often used for bulk database writes. Decide whether the batch is atomic in the database or committed record-by-record.

### 10.1 One Database Transaction for the Whole Batch

If the entire batch runs inside one database transaction, an error midway rolls back all changes in the batch. Whole-batch retry can fit because side effects from the prior attempt were rolled back.

Example:

~~~java
@Transactional
public void processBatch(List<OrderCreated> events) {
    for (OrderCreated event : events) {
        repository.save(toEntity(event));
    }
}
~~~

This snippet illustrates a database transaction. Ensure the listener actually invokes through Spring's transaction proxy and that the transaction boundary covers the whole batch.

If the transaction rolls back completely, retrying the batch creates no duplicates from rolled-back DB changes. However, side effects outside the database transaction such as HTTP calls or emails may still have happened.

### 10.2 Per-Record Commits

If the listener processes and commits each record individually, part of the batch may already be durably persisted before a later record fails.

In this case:

- Whole-batch retry may re-write earlier records.
- Partial retry with BatchListenerFailedException shrinks the portion that must be reprocessed.
- Idempotency or unique constraints are still needed to guard against duplicates.
- Track event IDs and processing states for reconciliation.

Do not assume a `@Transactional` annotation on a helper method wraps the entire batch in one transaction if the method is self-invoked within the same bean without going through a Spring proxy.

### 10.3 Idempotency Keys

One safeguard is using a unique event ID or business key. For example, a database table has a unique constraint on event_id. When a record is redelivered, the application detects the event was already processed and avoids repeating the side effect.

Idempotency should live at the data-write boundary or downstream call, not merely in an in-memory variable. After a restart, memory is wiped while duplicate records can still be redelivered.

## 11. Choosing Whole-Batch Retry vs. Partial Batch Retry

The two strategies fit different error categories.

| Criterion | Whole-Batch Retry | Partial Batch Retry |
|---|---|---|
| Know failed record | Not required | Must know precisely |
| Typical exception | Generic RuntimeException | BatchListenerFailedException |
| Reprocessing scope | Entire batch | Failed record and subsequent slice |
| Preceding records | May re-run | Can be committed and skipped |
| Listener complexity | Lower | Higher, must preserve exact index/record |
| Best suited for | Batch-wide errors or unidentifiable record | Pinpointable individual errors |
| Duplicate risk | Higher if prior side effects committed | Lower, though idempotency still required |
| Processing order | Retries entire group | Keeps pre-error slice, reprocesses from error onward |

### 11.1 When Should You Retry the Whole Batch?

- Database or downstream is unavailable for the whole batch.
- Batch processing uses an atomic transaction.
- Cannot reliably pinpoint the failed record.
- Cost of retrying the entire batch is low.
- Listener is designed to be idempotent.

### 11.2 When Should You Use Partial Retry?

- Listener processes records sequentially and can pinpoint failures accurately.
- One invalid data record fails while earlier records already completed.
- Batches are large and whole-batch retry is expensive.
- You want to send the exact bad record to the DLT.
- Original index and metadata mapping can be maintained accurately.

If an error is systemic and affects every record, do not try to pin it on an arbitrary index. Let the handler retry the whole batch with backoff until the dependency recovers.

## 12. Batch Size, Concurrency, and Retry Duration

Batch retries affect throughput more strongly than single-record retries. Tune batch size and concurrency together.

### 12.1 Large Batch Sizes

Large batches amortize overhead and can boost throughput, but:

- The listener takes longer to finish.
- One failing record can force many records to retry.
- More memory is needed to hold the batch.
- Database transactions can run longer.
- Easier to exceed poll timeouts if processing is slow.

### 12.2 High Concurrency

Increasing concurrency creates more consumers and more parallel batch listener invocations. This can send multiple concurrent batches into downstreams.

For instance, three pods with concurrency 4 can have up to 12 consumers processing batches concurrently. If each batch holds up to 100 records, total records in flight across invocations can be substantial. While 1,200 records will not always be in flight simultaneously, the figure shows the peak load to plan for during design.

### 12.3 max.poll.interval.ms

If batch processing runs too long, the consumer can exceed max.poll.interval.ms and be considered stuck. The group may rebalance, partitions reassign, and uncommitted records redeliver.

Measure p95/p99 batch processing duration, records per batch, and retry time. Set max.poll.interval.ms with appropriate headroom; never use huge values to mask a permanently hung listener.

## 13. Observing Batch Retries in Production

Track metrics by listener, group, topic, partition, and child consumer to see which batches are retrying.

Signals to collect:

| Category | Metrics/Logs to Observe |
|---|---|
| Batch listener | Batch size, processing duration, batch success/error counts |
| Retry | Retry count, backoff duration, exception type, current attempt |
| Recovery | Recovery success/failure, DLT publish rate, recoverer exceptions |
| Consumer | Consumer lag, poll interval, rebalances, commit latency |
| Partition | Assigned partitions, offset progression, stalled partitions |
| Downstream | Database pool, query latency, timeouts, HTTP error rate |
| Business | Event ID, batch ID, succeeded record count, failed record count, duplicate detection |

When logging batch failures, include:

- Listener ID and group ID.
- Topic, partition, offset of the failed record.
- Batch index if available.
- Event ID/business key.
- Exception class and root cause.
- Retry count or recovery attempt.

Do not log full sensitive payloads. Use event IDs and metadata for traceability.

### 13.1 Distinguishing Batch Errors from Single-Record Errors

If multiple batches fail with the same exception such as database timeout, a downstream may be experiencing a broad outage. If only one event ID fails repeatedly while other records succeed normally, it is likely a poison record or invalid data.

Never raise retry counts based solely on error frequency. Classify the root cause and blast radius first.

### 13.2 Tracking Progress After Recovery

After a record moves to the DLT or recovers successfully, confirm:

- Partition offsets continue advancing.
- Consumer lag decreases.
- Subsequent records are processed.
- DLT publish succeeded.
- Business side effects are not duplicated.
- No recovery exceptions were swallowed.

## 14. Investigation Procedure When a Batch Listener Retries Repeatedly

When a listener retries a batch repeatedly or a partition stalls:

1. Identify listener ID, group ID, topic, partition, and start time.
2. Record batch size, offsets, and event IDs in the batch.
3. Determine whether the listener threw a regular exception or BatchListenerFailedException.
4. If using BatchListenerFailedException, verify the index/record matches the original batch.
5. Inspect BackOff, retry count, and exception classification.
6. Determine whether the failed record is a poison message or a broad downstream outage.
7. Check database transactions, connection pools, and completed side effects.
8. Inspect consumer poll intervals, rebalances, and offset commits.
9. Verify the recoverer/DLT is healthy and the destination topic has enough partitions.
10. After fixing the issue, confirm the batch advances, offsets commit properly, and duplicates are controlled.

Do not reset offsets or delete records as soon as repeated retries appear. First identify which record failed, which side effects ran, and whether the batch is on the fallback path or partial-failure path.

## 15. Misconceptions to Avoid

**“When a batch listener fails, Spring always knows which record caused it.”** False. If the listener throws a regular exception, the handler has no index; fallback batch retry may retry the whole batch.

**“BatchListenerFailedException is just an exception by another name.”** False. It provides the failed record/index to the error handler for partial batch handling.

**“The index in BatchListenerFailedException is the Kafka offset.”** False. Index is the position in the batch received by the listener; offset is the record's position in a partition.

**“Records before the failed record are always reprocessed.”** Not necessarily. When the failed index is identified accurately, the handler can commit the preceding portion and retry from the failed record onward.

**“A successful retry means side effects happened only once.”** False. Side effects may have committed before the exception. Transactions or idempotency are required.

**“A successful DLT publish means business processing is complete.”** False. The DLT only quarantines the record for investigation or replay; the business still needs follow-up handling.

**“Increasing max.poll.interval.ms fixes every batch retry issue.”** False. It only changes the time limit between polls; it does not fix poison records, downstream outages, or hung listeners.

**“Whole-batch retry is always safe.”** False if preceding records produced durable side effects. Atomic transactions or idempotency are needed.

**“Higher concurrency always makes batch retries faster.”** Not necessarily. Downstreams can become more overloaded, and partition count still caps consumer assignment.

**“DefaultErrorHandler and transactional rollback handlers always behave the same.”** False. With transactional listeners, exceptions usually roll back the Kafka transaction and post-rollback handling belongs to AfterRollbackProcessor. Configure for the actual transaction model.

## 16. Transactional Batch Listeners: Key Distinctions

DefaultErrorHandler is typically used for non-transactional containers. If a listener container uses Kafka transactions, an exception in the listener rolls back the transaction. Spring Kafka uses a post-rollback mechanism, typically DefaultAfterRollbackProcessor, to handle redelivery/recovery per configuration.

Therefore:

- Do not assume DefaultErrorHandler is the sole error-handling mechanism for transactional containers.
- Distinguish Kafka transactions from database transactions.
- Clarify whether batch input offsets and output records share the same Kafka transaction.
- Check whether recovery/DLT publishing happens in a new transaction.
- Test rollback and redelivery on your exact factory and Spring Kafka version.

If a batch listener consumes inputs and produces outputs in a transaction, an error on any record can roll back the entire transaction by design. In that case, outputs inside the transaction are invisible to `read_committed` consumers and input offsets remain uncommitted in that transaction. External side effects outside Kafka still require idempotency/outbox or separate coordination.

## 17. Testing Batch Listener Retries

Test in an integration environment with multi-partition topics and easily traceable record IDs.

### 17.1 Whole-Batch Retry

- Configure a batch listener and DefaultErrorHandler with FixedBackOff.
- Send a batch with multiple records.
- Throw a regular exception while processing a record.
- Verify fallback retry re-invokes the listener with the batch per your version's behavior.
- Verify records before the failure may be reprocessed.
- Verify idempotency or transactions protect side effects.

### 17.2 Partial Batch Retry

- Send a batch with at least five records.
- Process the first two records successfully.
- Deliberately fail the third record.
- Throw BatchListenerFailedException with the correct index.
- Verify offsets for the pre-error portion commit per handler semantics.
- Verify the failed record and subsequent portion are reprocessed.
- Recover the failed record and confirm the batch keeps progressing.

### 17.3 Recovery and DLT

- Configure a recoverer sending failed records to a DLT.
- Keep failing a record until retries exhaust.
- Verify the DLT receives the right event ID, topic, partition, offset, and exception metadata.
- Temporarily make the DLT unavailable to test recovery failure.
- Verify the record is not treated as recovered when publishing fails.
- Replay a record after fixing the data and check for duplicates.

### 17.4 Exception Classification

- Send a record causing a transient exception and verify retries.
- Send a record causing a non-retryable exception and verify it follows the recovery policy.
- Verify downstream errors do not trigger a retry storm.
- Inspect logs for exception class and retry count.

### 17.5 Rebalances and Poll Intervals

- Create a batch processing duration close to the poll interval limit.
- Check whether the consumer triggers a rebalance.
- Create a backoff long enough to observe container lifecycle behavior.
- Verify the container keeps polling/pausing per framework mechanics.
- Verify uncommitted records redeliver safely after restart.

Never run fault injection in production without scope, approval, and a kill switch. Every test case must document expected results, batch ID, event ID, offset, and recovery evidence.

## 18. Configuration and Operations Checklist

**Batch listener**

- [ ] Correct listener factory is configured in batch mode.
- [ ] Batch size fits throughput, memory, and processing duration.
- [ ] Listener does not assume batch index equals Kafka offset.
- [ ] When the failed record is known, listener throws BatchListenerFailedException with exact index/record.
- [ ] When the failed record is unknown, whole-batch retry is acceptable and side effects are idempotent.

**DefaultErrorHandler**

- [ ] BackOff has explicit retry count and wait intervals.
- [ ] Retryable and non-retryable exceptions are classified.
- [ ] Recoverer is configured and tested.
- [ ] DLT has enough partitions if preserving source partition numbers.
- [ ] Recovery failures are not treated as success.
- [ ] Transactional containers use an appropriate rollback/recovery mechanism.

**Offsets and side effects**

- [ ] Ack mode matches batch listener usage.
- [ ] Offsets commit only after corresponding processing finishes.
- [ ] Partial batch commits are understood per topic-partition.
- [ ] Database transaction boundaries are clear.
- [ ] Event IDs or idempotency keys guard against duplicates.
- [ ] Async work is not acknowledged before completion.

**Observability and testing**

- [ ] Metrics exist for batch size, processing duration, retries, and recovery.
- [ ] Logs include listener ID, group ID, topic, partition, offset, and event ID.
- [ ] Consumer lag, rebalances, and poll intervals are monitored.
- [ ] Tested both fallback batch retry and partial batch retry.
- [ ] Tested DLT failures, replay, and duplicate handling.
- [ ] Runbook exists for investigating stuck batches and failed recoveries.

Batch retry strategy should be chosen based on whether failing records can be pinpointed and where side-effect boundaries lie. When errors affect the whole batch or the failing position cannot be determined, whole-batch retry is appropriate provided side effects are safe to repeat. When the failing record is identifiable, BatchListenerFailedException lets DefaultErrorHandler commit the already-processed portion and retry from the error position onward. Combining bounded BackOff, clear recovery, timely offset commits, and idempotency keeps batch listeners moving forward while protecting business data.


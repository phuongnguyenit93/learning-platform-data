# Synchronous Retry in Listeners

In Spring Kafka, synchronous retry is a way of re-attempting record processing directly on the listener container's consumer thread when the listener throws an exception. The container retains control over reading and acknowledging offsets, applies a backoff between attempts, and then decides whether to continue, recover the record, or send the record to a dead-letter topic (DLT).

This approach is typically implemented using **DefaultErrorHandler** and a **BackOff** policy. Because retries happen on the consumer thread processing that partition, it is easy to implement and preserves in-partition processing order by default. In return, retry time slows down the consumer owning the partition; if it waits too long, the consumer may miss its poll deadline, causing lag or a rebalance.

This lesson belongs to the **Retry** chapter of the **SPRING_KAFKA_MESSAGING** module, focusing on how to configure synchronous retry in listeners, classify retryable errors, control attempt counts, and safely recover failed records.

## Learning Outcomes

After this lesson, you can:

- Explain how synchronous retry in the listener container works.
- Distinguish the initial record delivery from subsequent redeliveries.
- Configure DefaultErrorHandler with FixedBackOff or a bounded backoff.
- Classify transient exceptions versus non-recoverable exceptions.
- Understand how seek and redelivery affect offsets, partitions, and ordering.
- Route exhausted records to a DLT using DeadLetterPublishingRecoverer.
- Evaluate the impact of backoff on the poll loop, consumer lag, and rebalances.
- Design idempotent listeners to withstand repeated processing.
- Distinguish blocking retry from non-blocking retry using retry topics.
- Test retry counts, recovery, DLT, and offset commits.

## 1. What Is Synchronous Retry?

The consumer polls records from Kafka and the listener container invokes the listener method to process them. If the listener completes normally, the container proceeds according to its AckMode and commits offsets appropriately. If the listener throws an exception, the container delegates the error to CommonErrorHandler.

With DefaultErrorHandler, the container can wait according to a BackOff and then redeliver the record for the listener to try processing again. This process is called blocking or synchronous retry because the consumer thread handling that record must wait for the retry attempts to complete before continuing normally.

~~~mermaid
flowchart TD
    P[Consumer poll] --> L[Invoke listener]
    L --> S{Listener succeeds?}
    S -->|Yes| C[Commit according to AckMode]
    S -->|No| E[DefaultErrorHandler]
    E --> B[Wait according to BackOff]
    B --> R{Retries remain?}
    R -->|Yes| L
    R -->|No| D[Recover record]
    D --> DL[Continue or publish to DLT]
~~~

Synchronous retry is suitable when an error is likely to resolve itself after a short interval, for example:

- The database is temporarily not accepting connections.
- An HTTP service returns a 503 error for a short period.
- A dependency times out due to a sudden traffic spike.
- A resource is temporarily unavailable.

If a record contains malformed data, lacks a required field, or violates a fixed business rule, retrying the same payload usually does not resolve the root cause. These errors should be classified as non-retryable or retried only very sparingly before recovery.

## 2. Processing Flow of DefaultErrorHandler

DefaultErrorHandler is Spring Kafka's standard error handler for non-transactional listener containers. It manages retries, backoff, exception classification, and recovery after attempts are exhausted.

General steps:

1. The consumer polls records.
2. The container invokes the listener.
3. The listener throws an exception.
4. DefaultErrorHandler receives the exception and determines the retry policy.
5. BackOff determines the wait interval and the next attempt.
6. The container seeks/redelivers the record according to the error handler mechanism.
7. If an attempt succeeds, the container continues processing.
8. If retries are exhausted, the recoverer is invoked to handle the record one final time.

In a record listener, the error handler can seek back to the failed offset and any unprocessed records in the poll so they are redelivered. Therefore, when one record fails, subsequent records in the same partition may have to wait until that record finishes processing. This helps preserve default ordering within the partition.

Retry should not be misunderstood as a loop calling the listener method again within the same stack frame. With DefaultErrorHandler, redelivery is coordinated with the container's consumer poll/seek cycle.

## 3. Configuring FixedBackOff

FixedBackOff uses a fixed wait interval between attempts and a maximum number of retries.

Example listener container configuration:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> dltKafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                    dltKafkaTemplate,
                    (record, exception) -> new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()
                    )
            );

    FixedBackOff backOff = new FixedBackOff(
            1_000L, // wait 1 second between retry attempts
            2L     // maximum 2 retries after the initial delivery
    );

    return new DefaultErrorHandler(recoverer, backOff);
}
~~~

Attaching the error handler to the factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
orderKafkaListenerFactory(
        ConsumerFactory<String, OrderCreatedEvent> consumerFactory,
        DefaultErrorHandler kafkaErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.RECORD);

    return factory;
}
~~~

With the illustrative configuration above, the record is delivered once initially, followed by up to two retries with a one-second wait between retries. If it still fails, the recoverer is invoked.

The retry count does not include the initial delivery. When documenting the policy for the operations team, state clearly whether you mean "2 retries" or "3 total deliveries" to avoid misunderstandings.

The DLT template and destination resolver must match the key/value serializers and partition count of the target topic. If you do not want to use a DLT, you can configure a different recoverer to log the error or skip the record as an intentional business decision.

## 4. Configuring DefaultErrorHandler in Spring Boot

Spring Boot provides an auto-configured listener container factory. You can create a DefaultErrorHandler bean and attach it to a custom factory as in the previous example, or configure the factory via a customizer mechanism appropriate for your Spring Boot version.

Listener using the factory:

~~~java
@Component
public class OrderCreatedListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-fulfillment",
            containerFactory = "orderKafkaListenerFactory"
    )
    public void consume(OrderCreatedEvent event) {
        orderService.handle(event);
    }
}
~~~

If an application has multiple listeners with different retry policies, you can create multiple container factories and bind each listener to the corresponding factory. Avoid sharing a single error handler with an overly long backoff across all streams if their SLAs and failure modes differ.

In modern Spring Kafka, CommonErrorHandler is the abstraction used by the listener container. DefaultErrorHandler is the standard error-handling implementation. Older examples using SeekToCurrentErrorHandler belong to earlier versions; when upgrading Spring Kafka, use the API compatible with your current dependency.

## 5. Exception Classification: Which Errors Should Be Retried?

Not every exception should be retried. Classification should be based on root cause and recoverability.

| Error type | Example | Typically appropriate policy |
|---|---|---|
| Transient error | Timeout, HTTP 503, database connection reset | Bounded retry with backoff. |
| Fixed data error | Malformed payload, missing required field, invalid enum | No retry, or very few retries before DLT. |
| Business error unresolvable by waiting | Order already canceled, disallowed state | Recover or route to separate business handling. |
| Configuration error | Wrong endpoint, expired credential, schema mapping mismatch | Alert and fix configuration; continuous retries usually do not help. |
| Load-dependent error | Exhausted connection pool, overloaded downstream | Retry with backoff while limiting concurrency and load. |

DefaultErrorHandler classifies certain exceptions as non-retryable by default. The application can add retryable or non-retryable exception types as required.

Example:

~~~java
DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, new FixedBackOff(1_000L, 2L));

handler.addNotRetryableExceptions(
        IllegalArgumentException.class
);

handler.addRetryableExceptions(
        TransientDataAccessException.class
);
~~~

This example treats IllegalArgumentException as non-retryable and TransientDataAccessException as retryable. Choose application-specific exceptions; avoid classifying a broad parent exception class because you may accidentally retry fixed data errors.

If you need to decide retry behavior based on record content or nested exceptions, you can use DefaultErrorHandler's exception classifier or backoff function. That configuration should be tested against the actual exceptions thrown by the listener.

## 6. Backoff and Retry Limits

Backoff introduces a pause between attempts to avoid hammering a dependency while it is experiencing issues.

Common options:

- Fixed backoff: constant pause, easy to predict.
- Exponential backoff: increases the pause after each failure.
- Bounded exponential backoff: increases gradually without exceeding a maximum interval.
- Backoff with jitter: adds randomness so multiple consumers do not retry at the exact same moment.

For example, an exponential backoff sequence might be 500 ms, 1 second, 2 seconds, and then cap at a maximum of 5 seconds. These numbers are only illustrative; the actual policy must match the SLA and recovery time of the dependency.

When choosing a backoff, determine:

1. Number of retries after the initial delivery.
2. Initial wait interval.
3. Multiplier factor.
4. Maximum wait interval.
5. Total time a record can be held in retry.
6. Action after retries are exhausted.

Never use infinite retries for unknown errors. A single failing record can stall a partition for a long time and cause consumer lag to grow continuously.

## 7. How Seek and Redelivery Affect Partitions

Kafka preserves record ordering within each partition. When a record fails, DefaultErrorHandler typically uses seek to tell the consumer to re-read the failed record and any subsequent unprocessed records from the poll.

Example partition with offsets:

~~~text
Offset:       10   11   12   13
Processing:   OK   OK   FAIL ...
                         |
                         +-- retry offset 12
~~~

If offset 12 fails, the container can redeliver offset 12 before proceeding to offset 13. Once the retry succeeds, the consumer advances.

In a consumer owning multiple partitions, retrying one record can affect the processing time of other records polled by that consumer. Partitions managed by other consumer members can still continue processing.

There is no global ordering across partitions. Retry preserves the container's in-partition ordering mechanism, but external side effects can still be duplicated or complete out of order if the listener offloads work to another thread.

## 8. Impact of Synchronous Retry on the Poll Loop and max.poll.interval.ms

The consumer must continue calling poll within the `max.poll.interval.ms` limit. With synchronous retry, record processing time and backoff intervals add up and can delay the consumer's next poll call.

Example:

- Initial processing takes 2 seconds.
- Retry 1 waits 5 seconds and processes for 2 seconds.
- Retry 2 waits 10 seconds and processes for 2 seconds.

The total time can exceed 20 seconds, excluding commit and other processing overhead. If the interval between polls exceeds `max.poll.interval.ms`, the consumer can leave the group and trigger a rebalance.

For long backoffs, Spring Kafka provides ContainerPausingBackOffHandler in supported versions. This mechanism pauses the container during the wait period and continues polling to maintain consumer group membership. The actual pause duration depends on the poll timeout and may not be accurate down to the millisecond.

Options when using long backoffs:

- Use ContainerPausingBackOffHandler if supported by your Spring Kafka version.
- Tune `max.poll.interval.ms` based on measured processing times.
- Reduce the retry count or total retry duration.
- Switch to non-blocking retry topics if you do not need to hold the partition waiting for failed records.
- Improve the dependency or move long-running work out of the listener.

Do not increase `max.poll.interval.ms` indefinitely to mask a slow listener. Measure p95/p99 processing times and determine the maximum possible wait time.

## 9. Synchronous Retry and Processing Order

Synchronous retry is generally appropriate when record order within a partition must be preserved. If the record at offset 20 fails, the record at offset 21 in the same partition normally waits until the failed record is processed or recovered before the stream continues.

This matters for events such as:

- OrderCreated before OrderPaid.
- AccountOpened before AccountDebited.
- InventoryReserved before InventoryReleased.

If a failed record is skipped and processing continues immediately, downstream business logic may run against an incorrect state. Conversely, if a failed record is retried for too long, the partition will be blocked and lag will accumulate.

Choose a policy based on the business contract:

- If ordering is mandatory, use bounded retries followed by controlled recovery.
- If failed records can be isolated, a DLT and replay procedure allow the partition to move forward.
- If records are independent, consider per-partition concurrency or non-blocking retry topics.
- If parallel processing within a single partition is needed, design sequence/ordering and offset management carefully yourself; do not assume default retry still preserves side-effect completion order.

## 10. DeadLetterPublishingRecoverer After Exhausting Retries

Once retries are exhausted, DefaultErrorHandler invokes a recoverer to handle the record. DeadLetterPublishingRecoverer is a common choice to publish failed records to a DLT.

Example destination resolver sending records to the source topic plus a `.DLT` suffix while keeping the same partition number:

~~~java
@Bean
DeadLetterPublishingRecoverer recoverer(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    return new DeadLetterPublishingRecoverer(
            kafkaTemplate,
            (record, exception) -> new TopicPartition(
                    record.topic() + ".DLT",
                    record.partition()
            )
    );
}
~~~

If the resolver preserves the partition number, the DLT topic must have enough matching partitions. You can choose a centralized single-partition DLT or another distribution rule, but you should evaluate throughput and traceability.

The DLT should retain source metadata such as topic, partition, offset, and exception details. Configure serializers compatible with both deserialized records and raw bytes in case deserialization fails.

Successful recovery allows the container to proceed according to the error handler's commit policy. If publishing to the DLT fails, do not assume the record was handled; configure and test behavior when the recoverer throws an exception.

## 11. Idempotency Because Records Can Be Redelivered

Retries and redeliveries mean a record may be processed by the listener multiple times. Even if the listener has already updated the database successfully, the consumer might stop before the offset is committed. When the group re-reads from the old offset, the same record arrives at the listener again.

Example debit handler:

~~~java
public void handle(PaymentRequested event) {
    paymentRepository.debit(
            event.accountId(),
            event.amount()
    );
}
~~~

If the listener runs again for the same event, the account could be debited twice.

You can use `eventId` as an idempotency key:

~~~java
@Transactional
public void handle(PaymentRequested event) {
    if (processedEventRepository.existsById(event.eventId())) {
        return;
    }

    accountRepository.debit(
            event.accountId(),
            event.amount()
    );

    processedEventRepository.save(
            new ProcessedEvent(event.eventId())
    );
}
~~~

In production implementations, checking and recording `eventId` must be protected by a unique constraint or appropriate transaction so two concurrent executions cannot both pass the check.

Idempotency must cover the initial attempt, retries within the same process, and redeliveries after restarts or rebalances. Retry does not turn a consumer into an exactly-once processor.

## 12. Batch Listeners and Retrying Failed Records

With a record listener, the error handler knows the exact record that failed. With a batch listener, the method receives multiple records in one invocation; when one record fails, the application must tell the error handler which record or index failed.

Spring Kafka provides `BatchListenerFailedException` to identify the failing record in a batch:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-batch"
)
public void consume(List<ConsumerRecord<String, OrderCreatedEvent>> records) {
    for (ConsumerRecord<String, OrderCreatedEvent> record : records) {
        try {
            orderService.handle(record.value());
        } catch (Exception exception) {
            throw new BatchListenerFailedException(
                    "Failed to process order event",
                    record
            );
        }
    }
}
~~~

When the error handler knows the failing record's position, it can commit/acknowledge the preceding portion and retry/recover the failing record and the remainder according to batch listener semantics.

If a batch listener throws a generic exception without identifying the failing record, the error handler may have to reprocess the entire batch. Records that already produced side effects before the failure may be processed again, so idempotency remains essential.

Partial batch and offset behavior depends on AckMode, Spring Kafka version, and error handler configuration. Test with a multi-partition batch and a failing record in the middle.

## 13. Blocking Retry vs. Non-Blocking Retry Topics

Spring Kafka supports multiple retry strategies. Blocking retry holds the record on the current consumer thread and retries before the partition advances. Non-blocking retry typically uses retry topics to move the record to a waiting topic while the consumer continues processing other records.

| Criterion | Blocking retry | Non-blocking retry |
|---|---|---|
| Mechanism | Error handler waits and redelivers the record | Publishes the record to a retry topic for later processing |
| Source partition | Can be blocked at the failed record | Can continue once the record is successfully forwarded |
| Ordering | Easier to preserve order within the partition | Can alter completion order across records |
| Long backoff | Can keep the consumer busy or pause the container | Better suited for long wait durations |
| Operations | Fewer auxiliary topics | Requires managing retry topics, consumers, and DLT |
| Use case | Transient errors, short recovery times, ordering important | Long retries, do not want to stall partition, ordering changes acceptable |

Non-blocking retry in Spring Kafka is commonly configured via `@RetryableTopic` or `RetryTopicConfiguration`. This is a different mechanism from `DefaultErrorHandler` blocking retry. Do not configure both in an overlapping way without defining a clear strategy.

If aggregate ordering is mandatory, carefully evaluate routing records to a retry topic because newer records in the main topic may be processed ahead of a record waiting for retry.

## 14. Retry When Listeners Use Transactions

When a listener container is configured with Kafka transactions, a listener error can roll back the transaction. In a transactional model, Spring Kafka typically uses `DefaultAfterRollbackProcessor` to handle records after rollback, rather than mechanically applying `DefaultErrorHandler` like in a non-transactional flow.

After rollback, the record can be redelivered according to the processor's policy; after a configured number of attempts, it can be recovered or published to a DLT. When using transactions, understand the boundary between transactional output records and input offsets.

Do not mix non-transactional `DefaultErrorHandler` examples into a transactional listener without checking the semantics of your Spring Kafka version. Configure `DefaultAfterRollbackProcessor` and the corresponding transaction manager, then test rollback, retry, recovery, and offset commits.

## 15. Common Pitfalls When Configuring Retry

| Mistake | Consequence | Resolution |
|---|---|---|
| Retrying every exception | Fixed data errors are retried repeatedly | Classify retryable vs. non-retryable errors. |
| Backoff too long | Consumer misses poll, lag grows, possible rebalance | Calculate total retry duration and consider a pause handler. |
| Infinite retries | Partition may stop making progress | Set retry limits and recovery. |
| Missing DLT or recoverer | Exhausted records have no follow-up handling | Define a clear recovery action. |
| DLT publish fails yet treated as success | Failed records may be lost from the main flow | Verify recoverer failure behavior. |
| Listener produces non-idempotent side effects | Retries/redeliveries cause duplicate effects | Use `eventId` and transactions/unique constraints. |
| Using blocking retry for multi-hour backoffs | Holds partition and consumer waiting too long | Consider retry topics. |
| Not testing batch semantics | Entire batch may be reprocessed | Use `BatchListenerFailedException` and test partial failures. |
| Using `DefaultErrorHandler` as a transactional rollback processor | Wrong transaction recovery mechanism | Use `DefaultAfterRollbackProcessor` for transactional flows where appropriate. |

## 16. Testing Synchronous Retry

Tests must prove that the listener is invoked the expected number of times, that backoff is bounded, and that the record is recovered once retries are exhausted.

Scenarios:

| Test case | What to verify |
|---|---|
| First-attempt success | Listener processes only once, offset advances. |
| Fail once then succeed | Record is redelivered to listener and completes. |
| Fail until retries exhausted | Recoverer is invoked after the exact number of attempts. |
| Non-retryable exception | Normal retry attempts are skipped. |
| Retryable exception | Backoff and retries match configuration. |
| DLT success | Record reaches the expected DLT topic/partition. |
| DLT publish failure | Record is not falsely marked as successfully recovered. |
| Poll interval | Long backoff does not unexpectedly drop the consumer from the group. |
| Rebalance | Uncommitted records can be redelivered and handled idempotently. |
| Batch failure | Error handler identifies the failing record and partial batch semantics. |

Example using a counter in an integration test:

~~~java
AtomicInteger attempts = new AtomicInteger();

doAnswer(invocation -> {
    if (attempts.incrementAndGet() < 3) {
        throw new TransientDataAccessException("Temporary database issue") {};
    }
    return null;
}).when(orderService).handle(any(OrderCreatedEvent.class));
~~~

With `FixedBackOff` configured for two retries after the initial delivery, the test can verify that the service is called at most three times and then completes. If the service continues to fail, the test must verify that the recoverer/DLT receives the record.

Use EmbeddedKafka or Testcontainers to test real containers and offsets. Use Awaitility or a latch with a timeout to wait for results; do not use fixed `Thread.sleep` calls. Backoffs in tests can be shortened to a few milliseconds to keep the suite fast while preserving retry count semantics.

## 17. Observing and Operating Retry

Retries can mask dependency incidents if you only watch the final count of succeeded records. Retry and recovery activity must be monitored separately.

Metrics to include:

- Listener failure count by exception class.
- Retry count and exhausted-record count.
- Actual backoff duration and time a record spends in retry.
- Records published to the DLT.
- DLT publish failure count.
- Consumer lag per partition.
- Processing latency p95/p99.
- Rebalance count and reasons.
- Post-retry success rate.

Logs should include topic, partition, offset, key or `eventId`, attempt count, and root exception. Do not log full sensitive payloads.

Set alerts when retry rates spike, DLT backlog grows, consumer lag increases continuously, or a partition remains stuck at the same offset for too long. A DLT needs an owner and a runbook to investigate, fix the root cause, and perform controlled replays.

## 18. Capstone Exercise: Retrying Database Errors in OrderCreatedListener

Build a listener to handle `OrderCreatedEvent`. The database service occasionally times out but recovers after a short interval.

Requirements:

1. Create a `DefaultErrorHandler` for the listener container.
2. Configure `FixedBackOff` with a one-second interval and two retries.
3. Configure `TransientDataAccessException` as retryable.
4. Configure `IllegalArgumentException` as non-retryable.
5. Create a `DeadLetterPublishingRecoverer` to send exhausted records to `orders.created.DLT`.
6. Send a record that fails on the first and second attempts and succeeds on the third.
7. Send a record that always fails and verify the DLT receives the right record.
8. Send a record with invalid data and verify it is not retried per the classifier.
9. Measure processing time and consumer lag as backoff increases.
10. Test a long backoff and observe `max.poll.interval.ms`/rebalances.
11. Add `eventId` idempotency to handle redeliveries safely.
12. Write integration tests for retry count, DLT, offsets, and side effects.
13. Write a runbook for prolonged dependency outages.
14. Propose when to switch from blocking retry to retry topics.

The exercise is complete when you can demonstrate attempt counts, wait intervals, exception classification, recovery after exhausted retries, and safe duplicate handling.

## 19. Learning Sequence and Completion Criteria

| Stage | Core focus | Self-check criterion |
|---|---|---|
| 1. Error flow | Listener exceptions and CommonErrorHandler | Can describe the error flow from listener to error handler. |
| 2. Blocking retry | DefaultErrorHandler | Can explain redelivery on the consumer thread. |
| 3. BackOff | FixedBackOff and exponential backoff | Can calculate attempt counts and total retry duration. |
| 4. Classification | Retryable and non-retryable exceptions | Selects the right errors to retry. |
| 5. Recovery | Recoverer and DLT | Handles records after retries are exhausted. |
| 6. Poll loop | `max.poll.interval.ms` and pause handler | Evaluates risks of long backoffs. |
| 7. Ordering | Seek, redelivery, and partitions | Explains why a failed record can block subsequent records. |
| 8. Reliability | Idempotency and transactions | Avoids duplicate side effects on redelivery. |
| 9. Strategy | Blocking vs. non-blocking retry | Picks the right mechanism based on ordering and wait times. |
| 10. Testing | EmbeddedKafka/Testcontainers | Verifies retry count, recovery, and offsets. |

The lesson is complete when you can configure `DefaultErrorHandler` with explicit retry counts and backoff, classify exceptions by recoverability, route exhausted records into a recovery workflow, and explain the impact on partition ordering, the poll loop, and offsets.

Synchronous retry is simple and useful for transient errors with short recovery times. Because retry holds the consumer on the failed record, set limits, measure total wait time, keep listeners idempotent, and maintain a DLT and runbook for unprocessable records.

# Listener Invoked Repeatedly

In Spring Kafka, a listener can be invoked multiple times for the same record when a previous attempt fails or the consumer has not committed the offset. This is usually a consequence of at-least-once delivery: Kafka favors redelivering records to avoid data loss, so the application must tolerate duplicate processing.

When logs show the same event appearing multiple times, determine whether it is an intentional retry, redelivery after restart/rebalance, or two producers sending two identical records. Those three cases have different causes and fixes. Do not simply raise timeouts or concurrency before identifying which record is being redelivered and which offset was committed.

## 1. Distinguishing Retry, Redelivery, and Duplicate Events

| Phenomenon | Meaning | Common signs |
|---|---|---|
| Blocking retry | Error handler applies backoff and has the container redeliver the record on the consumer thread | Same topic-partition-offset appears multiple times within a short span |
| Non-blocking retry | Failed record is published to a retry topic and processed again by a listener | Same event ID appears on a retry topic with a new offset |
| Redelivery | Kafka redelivers a record because its offset was uncommitted or ownership shifted | Same topic-partition-offset appears after restart/rebalance |
| Duplicate publish | Producer sends the same business event as multiple Kafka records | Same event ID yet different topic/partition/offset |
| Duplicate side effect | One record is reprocessed and produces repeated business effects | Double charge, duplicate order, or duplicate notification for the same event |

A Kafka record is identified at the transport level by the triple of topic, partition, and offset. When a record is republished, it gets a new offset; therefore, you need a stable business-level event ID to correlate the same event across retry topics or republishes.

## 2. Record Processing Flow and Commit Timing

For a record listener, the container polls records from Kafka, invokes the listener, and then commits offsets according to the acknowledgment mode and container configuration. If the listener throws an exception, the error handler decides whether to retry, recover, or route the record to a DLT.

```text
Kafka partition
    |
    v
Consumer poll
    |
    v
Spring Kafka listener
    |
    +---- succeeds ----------------> commit offset
    |
    +---- throws exception
              |
              v
        Error handler
              |
        backoff / retry
              |
        +-----+----------------+
        |                      |
     retry again            recover
        |                      |
        v                      v
  listener again           DLT / skip
```

In common Spring Kafka setups, the Kafka consumer's auto-commit is disabled so the listener container manages commits. Exact commit behavior depends on `AckMode`, transactions, and listener type. Check your actual configuration instead of assuming that returning from the listener always commits the offset immediately.

A crucial rule: if a listener completes a side effect and the process crashes before the offset is committed, the record can be redelivered. That is why idempotent processing is mandatory for operations that must not repeat.

## 3. Common Reasons a Listener Runs Multiple Times

- Listener throws an exception and the error handler retries.
- Recoverer fails to publish to the DLT, leaving recovery incomplete.
- Container stops or JVM crashes after side effects occur but before commit.
- Consumer loses group membership or rebalances while processing.
- Processing time exceeds the poll limit, causing the consumer to leave the group and its partition to move to another member.
- Commit fails or does not occur under the expected `AckMode`.
- Application explicitly seeks/nacks to re-read records.
- Producer publishes the same event multiple times due to send retries or business-layer bugs.
- Two listeners or two applications with different group IDs subscribe to the same topic; each group receives an independent copy of the record.
- A retry topic delivers the record back to the listener according to the backoff schedule.
- A batch listener fails, causing part or all of the batch to be redelivered.

Inspect logs by group ID, topic, partition, offset, and event ID. If two distinct group IDs read the same topic, each group invoking its listener once is normal behavior, not Kafka delivering duplicates within one group. Searching only by message text or business key can mistake two distinct records for a retry.

## 4. Blocking Retry with `DefaultErrorHandler`

`DefaultErrorHandler` is the standard error handler for record listeners. When a listener throws an exception, the handler applies backoff and retries the record. During retries, the partition may pause at the failing record, holding back subsequent records on that partition.

Example retrying twice after the initial attempt:

```java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    DefaultErrorHandler handler =
            new DefaultErrorHandler(
                    recoverer,
                    new FixedBackOff(1_000L, 2L)
            );

    return handler;
}
```

With `FixedBackOff(1_000L, 2L)`, the handler waits one second between retries and performs two retries after the first invocation: up to three total attempts before recovery. The second argument is the number of retries, not total calls.

Attach the handler on the listener container factory:

```java
factory.setCommonErrorHandler(kafkaErrorHandler);
```

With Spring Boot, registering a `CommonErrorHandler` bean can auto-configure the factory, or you can attach the handler to a custom factory. If multiple factories exist, verify the listener uses the right bean via `@KafkaListener`'s `containerFactory` attribute.

## 5. Choosing Which Exceptions to Retry

Not every failure should be retried. Transient errors like a database connection timeout or HTTP 503 may recover after a short wait. Data errors such as bad schemas, missing required fields, or violated business rules rarely heal on retry.

Exceptions can be classified:

```java
import org.springframework.kafka.support.ExponentialBackOffWithMaxRetries;

DefaultErrorHandler handler =
        new DefaultErrorHandler(
                recoverer,
                new ExponentialBackOffWithMaxRetries(4)
        );

handler.addNotRetryableExceptions(
        InvalidOrderException.class,
        UnsupportedEventVersionException.class
);
```

This example marks business exceptions as non-retryable. Non-retryable exceptions go straight to the recoverer according to the handler's classification. Configure exception classifiers intentionally and avoid treating every exception as retryable.

Some infrastructure errors are transient yet retrying too aggressively amplifies load on an already struggling dependency. Choose bounded backoff, and consider exponential backoff plus jitter when many consumers retry concurrently.

## 6. DLT and Failures During Recovery

Once retries are exhausted, `DeadLetterPublishingRecoverer` can publish the record to a dead-letter topic. If publishing to the DLT fails, recovery is incomplete; the source record should not be treated as successfully handled.

```java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
                dltKafkaTemplate,
                (record, exception) -> new TopicPartition(
                        record.topic() + ".DLT",
                        record.partition()
                )
        );

recoverer.setFailIfSendResultIsError(true);
```

When using partition mapping like the example, the DLT must have enough matching partitions. If the DLT has fewer partitions than the source topic, pick a different partition routing strategy or let the producer choose the partition.

When a listener keeps getting invoked even after retries should be exhausted, check:

- Did the DLT publish succeed?
- Can the DLT producer serialize the actual key/value?
- Did the recoverer throw due to send timeout or broker errors?
- Is the error handler attached to the right listener container?
- Is the offset committed after recovery per your `AckMode` and version?

Never swallow DLT publish failures. Losing a record from both the source topic and the DLT makes investigation and recovery far harder.

## 7. Non-Blocking Retry with `@RetryableTopic`

`@RetryableTopic` sends failed records to retry topics instead of blocking the source partition during backoff. The listener is invoked again when the record arrives on the retry topic per the configured schedule.

Example:

```java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(
                delay = 1_000,
                multiplier = 2.0,
                maxDelay = 10_000
        ),
        dltTopicSuffix = ".DLT"
)
@KafkaListener(
        topics = "orders",
        groupId = "orders-service"
)
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
```

`attempts` specifies total processing attempts, including the first attempt on the main topic. For instance, `attempts = "4"` means up to four processing attempts before the record moves to the DLT, per retry topic configuration semantics.

Non-blocking retry avoids stalling the main partition, yet it can alter business ordering: later records on the main topic can be processed ahead of a record waiting in a retry topic. Weigh this carefully if per-key ordering is mandatory.

Spring Kafka's non-blocking retry does not support batch listeners and does not combine with container transactions. Check the documentation for your Spring Kafka version before enabling it; if a listener requires batching or container transactions, pick a retry strategy compatible with those constraints.

## 8. How Do Blocking Retry and Non-Blocking Retry Differ?

| Criterion | Blocking retry | Non-blocking retry |
|---|---|---|
| Mechanism | Error handler retries on consumer/partition | Publishes to retry topics |
| Source partition | Can pause at the failing record | Can continue processing subsequent records |
| Ordering | Easier to preserve in-partition ordering | Can invert order between failed record and newer records |
| Extra topics | No extra retry topics per retry step | Requires retry topics and a DLT |
| Operations | Monitor backoff, retries, and DLT publishing | Monitor retry topics, routing, DLT, and multiple consumer groups |
| Best fit | Strict ordering, short retries, transient errors | Asynchronous tolerance and need to avoid blocking partitions |

Do not configure blocking retries with huge delays for unrecoverable errors. Conversely, non-blocking retry is unsuitable if business rules forbid newer records from overtaking an earlier record for the same key.

## 9. Offsets, `AckMode`, and Re-Invoked Listeners

`AckMode` governs when the container commits offsets after processing:

| `AckMode` | General behavior |
|---|---|
| `RECORD` | Commits after each record listener succeeds |
| `BATCH` | Commits after all records in the poll batch succeed |
| `MANUAL` | Listener calls `acknowledge`; container commits per mode semantics |
| `MANUAL_IMMEDIATE` | Commits immediately on acknowledge under matching thread/config conditions |

With `BATCH`, if one record in a batch fails, earlier records may already have run side effects before the batch is retried. Without idempotency, side effects for already-succeeded records can repeat.

With manual ack, acknowledge only after business work is durably complete per contract. Never ack before asynchronous work finishes. If a listener launches a future and returns without proper async acknowledgment support, the container can commit before side effects finish.

Do not commit early just to reduce lag if doing so sacrifices redelivery on processing failures.

### When the Listener Container Uses Kafka Transactions

If the container is configured with transactions, an exception from the listener rolls back the current transaction. Re-reading unprocessed records is handled by `DefaultAfterRollbackProcessor`; this flow differs from non-transactional record listeners using `DefaultErrorHandler`. Check the transaction manager, rollback behavior, backoff, and after-rollback processor recoverer before drawing conclusions about retry counts.

Kafka transactions can coordinate consuming and producing Kafka records atomically, yet they do not automatically roll back external databases or HTTP side effects. If a listener calls an external API before the transaction rolls back, redelivery can call that API again. Idempotency or outbox/inbox patterns are still required.

## 10. Listener Re-Invoked After Restart or Rebalance

Kafka stores committed offsets per group. If a consumer processed a record without committing the offset, a new consumer can re-read that record after a restart or rebalance.

Example:

```text
offset 100: listener succeeds, writes database
process crashes before commit
new consumer receives partition
offset 100 is read again
listener reprocesses the same record
```

This can happen even when the listener throws no exception. It is at-least-once behavior, not a Kafka bug.

Check:

- Shutdown and startup logs around the redelivery timestamp.
- Group member changes and rebalance events.
- Commit intervals, `AckMode`, and transactions.
- Processing time relative to `max.poll.interval.ms`.
- Whether side effects were already committed to the database.
- Whether the consumer was forcefully killed before graceful container shutdown.

## 11. Batch Listeners and Full-Batch Retries

With a batch listener, a single invocation can receive multiple records. If the listener throws a generic exception, the container may not know which record failed; depending on the handler, the entire batch can be retried.

When the failing record is known, throw `BatchListenerFailedException` with the record/index so the error handler handles succeeded vs. failed portions per supported semantics.

```java
@KafkaListener(
        topics = "orders",
        groupId = "orders-batch-service"
)
public void onOrders(List<ConsumerRecord<String, OrderEvent>> records) {
    for (int index = 0; index < records.size(); index++) {
        ConsumerRecord<String, OrderEvent> record = records.get(index);

        try {
            orderService.process(record.value());
        }
        catch (Exception exception) {
            throw new BatchListenerFailedException(
                    "Cannot process order",
                    exception,
                    index
            );
        }
    }
}
```

Use a compatible error handler and batch listener setup. Failing to identify the exact failed record index can cause full-batch retries that repeat side effects for earlier records.

## 12. Deserialization Failures Do Not Always Invoke the Listener

If a key or value cannot be deserialized, the error can happen before the listener method is called. Thus, seeing no listener invocations in logs does not prove the record is not being retried or recovered.

Use `ErrorHandlingDeserializer` to turn deserialization failures into header metadata so the container error handler can act. If the DLT must keep raw bytes, the DLT producer needs a serializer supporting byte arrays.

Distinguish:

- Deserializer failing before the listener.
- Message converter failing while converting the record into method arguments.
- Listener method executing and throwing an exception.
- Business validation failing after the DTO is constructed.

Each error occurs at a different layer and needs tailored logs/metrics. Do not just add a log line at the top of the listener and assume every retried record passes through it.

## 13. Measuring Invocations and Tracing a Single Record

To determine whether a listener is invoked repeatedly, log stable record metadata:

```java
@KafkaListener(
        topics = "orders",
        groupId = "orders-service"
)
public void onOrder(
        OrderEvent event,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset,
        @Header(name = KafkaHeaders.DELIVERY_ATTEMPT, required = false)
        Integer deliveryAttempt) {

    log.info(
            "Processing order eventId={}, topic={}, partition={}, offset={}, deliveryAttempt={}",
            event.eventId(),
            topic,
            partition,
            offset,
            deliveryAttempt
    );

    orderService.process(event);
}
```

Relevant imports in the example:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.kafka.support.KafkaHeaders;
```

Use the event ID to recognize the same business event; use topic-partition-offset to identify a specific Kafka record. When an event moves to a retry topic or is republished, topic/partition/offset change while the event ID can stay constant.

You can enable the delivery attempt header on the error handler in supported versions:

```java
handler.setDeliveryAttemptHeader(true);
```

Then read the delivery attempt header using your Spring Kafka version's API. Do not rely on this header as a global ID; it only tracks attempts within that error-handling scope.

Monitor as well:

- Listener invocation count.
- Retry attempt count.
- Recovery and DLT publish success/failure.
- Listener processing duration.
- Consumer lag and commit rate.
- Rebalance count and group member changes.
- Duplicate event IDs or duplicate business keys.

Do not log full payloads if they contain PII, tokens, or sensitive data.

## 14. Idempotency to Prevent Duplicate Side Effects

Retries and redeliveries cannot by themselves guarantee a side effect happens only once. Listeners must be designed idempotently whenever the same event might be processed more than once.

A common pattern is storing processed event IDs inside the same database transaction as the business update:

```sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Processing flow:

1. Start database transaction.
2. Attempt to insert the event ID into the processed events table protected by a unique constraint.
3. If the event ID already exists, exit without repeating side effects.
4. If the insert succeeds, apply business changes inside the same transaction.
5. Commit transaction.
6. Only after the listener returns does the container commit the Kafka offset per `AckMode`.

Never rely solely on check-then-insert without a unique constraint; two consumers or concurrent executions can both pass the check. A unique constraint or atomic insert is the real duplicate barrier.

For external APIs, pass a stable idempotency key if the provider supports it. For database-write-then-publish flows, consider transactional outbox. Event IDs should be generated by the producer and preserved across retries, DLTs, and replays.

Do not use Kafka offsets alone as business idempotency keys because a republished event receives a new offset.

## 15. Misconfigurations Causing Infinite Listener Retries

| Symptom | Possible cause | How to handle |
|---|---|---|
| Listener repeats continuously | Unbounded backoff/retries or exception always retryable | Set retry limits and classify exceptions |
| Listener repeats after DB write | Crash before Kafka commit or commit failed | Design idempotently and inspect commit logs |
| Listener never reaches DLT | Recoverer not attached to the right container factory or retries not exhausted | Check listener factory and retry counts |
| DLT publish fails | Serializer does not support value/key type or broker/topic unavailable | Check DLT producer, serializer, and send result |
| Partition stuck on one record | Blocking retry waiting or repeated recovery failures | Check backoff, exceptions, and recovery failures |
| Newer records processed before failing record | Non-blocking retry routed the record to a retry topic | Re-evaluate ordering requirements |
| Listener re-invoked after deploy | Offsets uncommitted before instance stopped | Graceful shutdown and idempotency |
| Batch produces duplicate side effects | Whole batch retried after one bad record | Use `BatchListenerFailedException` and idempotent handling |
| No listener logs on failing record | Deserialization/conversion failed before method invocation | Use `ErrorHandlingDeserializer` and log from error handler |
| Retries never stop on data errors | Business exception classified as retryable | Mark non-retryable and recover to DLT |

## 16. Runbook for Investigating Repeated Listener Invocations

When detecting the same event multiple times, follow these steps in order:

1. Extract event ID and topic, partition, offset metadata from logs.
2. Compare invocations: same offset or different offsets?
3. If same offset, check blocking retries, commits, restarts, and rebalances.
4. If different offsets yet same event ID, check producer retries, retry topics, DLT replays, or duplicate publishes.
5. Correlate timestamps with listener exceptions, error handler logs, and recovery outcomes.
6. Check `AckMode`, commit strategy, transactions, and processing duration.
7. Check whether DLT/retry topics had publish failures or routed records per config.
8. Determine whether side effects already occurred on an earlier attempt.
9. Verify idempotency keys/unique constraints and fix the processing path before replaying.
10. After fixing, monitor listener invocation count, lag, commits, and DLT backlog.

Do not delete records or reset offsets just to quiet repeated logs. Keep sufficient metadata to reproduce and investigate the incident.

## 17. Testing Retries and Redelivery

Use Embedded Kafka or Testcontainers to test against a real broker. Each test should use isolated topics/groups or clean state explicitly so offsets from prior tests do not leak.

Scenarios to verify:

| Scenario | Expected result |
|---|---|
| Listener throws twice then succeeds | Invocation count and backoff match configuration |
| Listener always throws | Exhausts retries then recovers/DLT |
| DLT producer fails | Recovery counts as failed; record is not treated as recovered |
| Listener writes DB then crashes before commit | Record can be redelivered yet side effects do not repeat due to idempotency |
| Consumer rebalances mid-processing | Record can be redelivered; side effects stay safe |
| Non-blocking retry | Record routes through retry topics and eventually to DLT |
| Batch listener fails on middle record | Only the portion needing retry is reprocessed per configured handler |
| Malformed JSON payload | Deserialization error is caught by the error handler |
| Non-retryable exception | Proceeds directly to recovery per classifier |
| Replayed event | Event ID stays intact and consumer avoids duplicate side effects |

Use Awaitility or polling assertions with finite deadlines instead of fixed sleeps. Assert listener invocation counts, offsets, event IDs, retry/DLT records, and database side-effect state. Never assert only that the listener eventually succeeded.

## 18. Checklist to Prevent and Handle Repeated Listener Invocations

1. Log event ID alongside topic, partition, and offset on every invocation.
2. Identify whether repetitions are blocking retries, non-blocking retries, or redeliveries after restart.
3. Configure bounded retries and suitable backoff.
4. Separate transient exceptions from non-retryable data errors.
5. Verify recoverer/DLT publish results.
6. Choose `AckMode` and commit strategy aligned with business completion.
7. Design idempotency using event IDs and unique constraints.
8. For batch listeners, identify failing records explicitly and understand retry semantics.
9. Monitor rebalances, `max.poll.interval.ms`, and graceful shutdown.
10. Test crash-before-commit, recovery failures, retry topics, and DLT replays.
11. Do not rely on identical log text alone as proof the same record was redelivered.
12. Replay only after fixing the root cause and ensuring side-effect safety.

Repeated listener invocations are typically symptoms of retries or at-least-once delivery. By tracing with event IDs and topic-partition-offset, understanding commits and rebalances, and building idempotent consumers, Spring Kafka applications can recover from failures without creating duplicate business effects.

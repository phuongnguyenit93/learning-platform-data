# How Retries Affect Partition Ordering

Kafka guarantees record order within a single partition by offset. However, the order written to the log and the order in which processing completes at the consumer are two different things. When a record fails and must be retried, the retry strategy determines whether the consumer waits for that record to finish before moving on or routes it to a separate stream so the partition can keep advancing.

With synchronous (blocking) retry in the listener container, the consumer typically reprocesses the failed record in place before continuing to subsequent records in the partition. This preserves processing order, though it can stall the partition while waiting. With retry topics (non-blocking retry), the failed record is sent to a retry topic so the original topic's consumer can keep reading; later records may complete before the record being retried. This improves consumption continuity but does not preserve initial ordering.

If business logic requires events for the same aggregate to be applied in strict order, choose the right retry strategy from the start. You cannot rely solely on the producer using the same key or Kafka storing records by offset to assume final processing order remains preserved.

## 1. At What Scope Does Kafka Guarantee Ordering?

Kafka guarantees ordering only within a single partition. Records appended to a partition receive monotonically increasing offsets; consumers read records from a partition in that order. Kafka does not provide a global order across partitions in the same topic or across multiple topics.

For example, topic `orders` has three partitions:

```text
orders-0: offset 10 -> offset 11 -> offset 12 -> ...
orders-1: offset 20 -> offset 21 -> offset 22 -> ...
orders-2: offset  5 -> offset  6 -> offset  7 -> ...
```

A consumer group can process all three partitions in parallel. Record offset 12 on partition 0 is not necessarily processed before record offset 21 on partition 1. If business logic requires ordering per `orderId`, the producer should use `orderId` as the key so events for the same order are routed to the same partition by a deterministic partitioner.

Example:

```java
kafkaTemplate.send("orders", event.orderId(), event);
```

Keys route events for the same order to the same partition, but they do not automatically guarantee the consumer completes business logic in order if the listener processes asynchronously or moves failed records to retry topics.

## 2. Distinguishing Append Order, Delivery Order, and Completion Order

When discussing ordering, clarify which stage you mean:

| Stage | Meaning |
|---|---|
| Producer append order | Order in which records are written to a partition |
| Consumer delivery order | Order in which records are returned to the consumer within a partition |
| Listener invocation order | Order in which the listener begins processing records |
| Business completion order | Order in which business side effects actually finish |
| Retry/replay order | Order in which records are reprocessed after failure |

Kafka manages log append order and consumer delivery order per partition. The application can still invert completion order if the listener dispatches work to a thread pool and returns immediately, processes multiple events from the same partition concurrently, or uses retry topics.

For example, a consumer receives offset 100 then 101 in order, but submits both to an executor:

```text
Received:   offset 100 -------- offset 101
Processed:  start 100            start 101
Completed:                   101 -------- 100
```

If event 101 updates order state before event 100, business data may regress or become corrupted even though Kafka delivered the records in order. When ordering matters, do not let the listener commit or finish before the corresponding work completes; if parallelism is needed, serialize work by key or check the aggregate's sequence/version.

## 3. Producers Must Also Preserve Order on Retries

Ordering can already be disrupted on the producer side if a send batch fails and the producer retries. Without producer idempotence enabled, if `max.in.flight.requests.per.connection` is greater than 1, a later batch can succeed before an earlier batch that is being retried, inverting record order in the partition.

To preserve order during producer retries, enable idempotence and use compatible settings:

```yaml
spring:
  kafka:
    producer:
      acks: all
      retries: 2147483647
      properties:
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
```

An idempotent producer uses sequence numbers so the broker recognizes retries of the same batch and avoids duplicate writes. With idempotence enabled, Kafka supports up to five in-flight requests per connection while preserving per-partition order. If idempotence is disabled, cap `max.in.flight.requests.per.connection` at 1 to prevent out-of-order retries, at the cost of lower throughput.

In modern Kafka clients, idempotence is often enabled by default when related settings are compatible; declaring it explicitly keeps the contract clear and prevents unintended changes. Producer idempotence only handles retries within a producer session; it does not prevent business duplicates caused by the application calling `send()` again as a new request.

## 4. Blocking Retry Preserves In-Partition Ordering

With a record listener, `DefaultErrorHandler` can retry a failing record by seeking the consumer back to that offset. Only after the failed record succeeds or is recovered per policy does the consumer move on to subsequent records.

Example on partition `orders-0`:

```text
Log:
offset 100: OrderUpdated(version=1)
offset 101: OrderUpdated(version=2)
offset 102: OrderUpdated(version=3)

Consumer:
1. Receive offset 100
2. Transient processing error
3. Backoff and retry offset 100
4. Offset 100 succeeds
5. Continue to offset 101, then 102
```

Because record 101 is not passed to the listener before offset 100 is handled/recovered, blocking retry preserves processing order within the partition. This is the right choice when events are causally linked and later events must not overtake earlier ones.

Configuration example:

```java
@Bean
DefaultErrorHandler orderErrorHandler(KafkaTemplate<Object, Object> dltTemplate) {
    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(dltTemplate);

    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);
    DefaultErrorHandler handler = new DefaultErrorHandler(recoverer, backOff);
    handler.setSeekAfterError(true);
    handler.addNotRetryableExceptions(InvalidOrderException.class);
    return handler;
}
```

`FixedBackOff(1000, 2)` waits one second between retries and allows two retries after the initial processing attempt. `setSeekAfterError(true)` explicitly states the strategy of seeking back to the failed record and remaining records. This is the standard default behavior of `DefaultErrorHandler`; you can leave it at default unless you want to state it explicitly.

## 5. Trade-off: Head-of-Line Blocking

Blocking retry preserves order by preventing later records from passing a failing record. The consequence is that a persistently failing record can stall the entire partition. This phenomenon is head-of-line blocking.

Example:

```text
Partition orders-0:

offset 100: Order A -> fails, 5 retries, total wait 30 seconds
offset 101: Order B -> waiting
offset 102: Order C -> waiting

While retrying offset 100:
  B and C are not yet processed by the listener on that consumer thread.
```

When a consumer thread handles multiple partitions, default blocking backoff can also prevent other partitions assigned to that same consumer thread from being processed by the listener while the thread waits. Other consumer threads in the group can still continue processing their own partitions.

Blocking retry fits when:

- Ordering is a mandatory business requirement.
- Errors are likely to recover quickly.
- Retry count and backoff are explicitly bounded.
- Throughput can tolerate a partition being temporarily stalled.

Do not use multi-minute blocking retries for every error type. A single poison message can cause lag to grow continuously and degrade partition throughput.

## 6. Configuring DefaultErrorHandler for In-Place Retry

Example record listener factory using blocking retry:

```java
@Configuration
public class OrderKafkaConfiguration {

    @Bean
    DefaultErrorHandler orderErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(kafkaTemplate);

        ExponentialBackOffWithMaxRetries backOff =
                new ExponentialBackOffWithMaxRetries(3);
        backOff.setInitialInterval(500L);
        backOff.setMultiplier(2.0);
        backOff.setMaxInterval(4_000L);

        DefaultErrorHandler handler =
                new DefaultErrorHandler(recoverer, backOff);
        handler.addNotRetryableExceptions(
                InvalidOrderException.class,
                UnsupportedOrderStateException.class);
        return handler;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            orderListenerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory,
                    DefaultErrorHandler orderErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(orderErrorHandler);
        factory.setConcurrency(3);
        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.RECORD);
        return factory;
    }
}
```

Synchronous listener:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-projection",
        containerFactory = "orderListenerFactory")
public void onOrder(OrderEvent event) {
    orderProjection.apply(event);
}
```

With `AckMode.RECORD`, the container acknowledges progress per record after the listener completes successfully. When the listener throws an error, the error handler applies retries and recovery. Ensure the DLT has enough partitions if the recoverer preserves the source partition, and verify DLT publishing succeeds before considering the original record recovered.

## 7. SeekAfterError and Record Retention Behavior

`DefaultErrorHandler` typically seeks the consumer back to the offset of the failed record and remaining records from the poll so they are returned on the next poll. This mechanism keeps the failed record from being skipped in the partition.

In supported Spring Kafka versions, you can set `seekAfterError(false)` so the container retains unprocessed records in memory and redelivers them after performing a brief poll to keep the consumer group alive. This avoids seeking the broker position in the usual way, yet still does not mean records after the failed record are processed ahead of it. The container preserves the order of the redelivered record list.

The two options differ in how the container manages remaining records; both aim to keep processing the failed record before subsequent ones in a blocking flow. Do not confuse `seekAfterError(false)` with non-blocking retry topics: it does not move the failed record to another topic so the original partition can move freely onward.

## 8. Non-Blocking Retry Topics Can Break Ordering

With non-blocking retry, a failed record is published to a retry topic. The original topic's consumer can move on to the next record without waiting for the failed record to finish retrying. This improves partition progress, but allows later records to overtake earlier ones.

Example with the same partition and same key:

```text
Topic orders, partition 0:
offset 100: OrderUpdated(version=1) -> error, routed to orders-retry-1000
offset 101: OrderUpdated(version=2) -> processed immediately with success

After delay:
orders-retry-1000:
version=1 -> retried and processed successfully

Business completion order: version 2 then version 1
```

Using the same key does not prevent this because the retried record resides on a different topic with its own consumer group and schedule. The retried record can return after a newer record has already updated business state.

Spring Kafka provides `@RetryableTopic` to configure retry topics:

```java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(
                delay = 1_000,
                multiplier = 2.0,
                maxDelay = 10_000))
@KafkaListener(topics = "orders", groupId = "order-projection")
public void onOrder(OrderEvent event) {
    orderProjection.apply(event);
}
```

In this example, `attempts` is the total number of attempts per retry-topic configuration, including the initial processing attempt; check your Spring Kafka version and exception policy to know which records move to retry topics. Specific retry topic configurations, partition counts, and naming strategies should be verified before deployment.

Non-blocking retry is suitable when:

- It is acceptable for newer events to be processed before an event being retried.
- Retry durations are long and you do not want to block the original partition.
- Business logic is idempotent and has version/sequence guards.
- Throughput and consumption continuity matter more than strict ordering.

## 9. Retry Topics and DLTs Are Separate Streams from the Source Partition

Retry topics and DLTs are separate topics with their own partitions, offsets, and consumer groups. Even if a retry topic is created with the same partition count and same key, ordering is only guaranteed within each partition of each topic. There is no shared offset to merge ordering between `orders-0` and `orders-retry-1000-0`.

Points to keep in mind:

- A partition resolver can preserve the source partition number, but does not establish cross-topic ordering.
- A retry-topic consumer may run slower or faster than the original topic consumer.
- Multiple retry levels can send records through topics with different wait durations.
- Records that exhaust retries and enter a DLT may be replayed hours later, after newer events have already been applied.
- Replaying a DLT by file order or timestamp does not necessarily restore the original partition order.

If ordered replay is needed, retain source metadata such as original topic, partition, offset, key, and event sequence. Replay tools should sort by partition and offset or by aggregate version, while preventing older events from overwriting newer state.

## 10. DLT Recovery Can Create Gaps in the Stream

Once retries are exhausted, the recoverer can publish the failed record to a DLT. If publishing succeeds and the error handler marks the record as recovered, the consumer advances to subsequent offsets. That means the original partition no longer waits for that record.

Example:

```text
orders-0:
offset 100: version 1 -> retries exhausted -> orders.DLT
offset 101: version 2 -> processed successfully
offset 102: version 3 -> processed successfully

Later:
orders.DLT:
original offset 100 -> investigated and replayed
```

If version 1 is replayed after version 3 has been applied, the projection could regress if the handler does not check versions. Under strict ordering, routing a record to a DLT and continuing the partition must not be mistaken for preserving full business order. It is a deliberate decision to skip an event temporarily and handle the resulting gap.

If the failed record is a prerequisite for all subsequent events, the safer option may be to stop/pause the partition or consumer, fix the issue, and resume. If business rules allow skipping, record the gap and maintain clear compensation/reconciliation rules.

## 11. Partition Concurrency Does Not Create Global Ordering

`concurrency` on `ConcurrentKafkaListenerContainerFactory` creates multiple consumers within the same group. Kafka assigns each partition to at most one consumer in a group at any given time. Therefore, concurrency enables parallel processing across partitions, without allowing multiple consumers to process records from the same partition in arbitrary order.

Example topic with 6 partitions and concurrency of 3:

```text
Consumer 1: partition 0, 1
Consumer 2: partition 2, 3
Consumer 3: partition 4, 5
```

Each consumer processes its assigned partitions in record order. However, if the listener uses an async executor or reactive pipeline and returns before processing finishes, business completion order can still be inverted. If parallel processing within a single partition is needed, enforce sequencing by key/aggregate and commit offsets only after earlier records complete.

Raising concurrency above the partition count does not add useful processing threads for that topic; excess consumers will sit idle without assigned partitions. Also consider rebalances during scale-up/down and their impact on in-flight progress.

## 12. Preserving Ordering During Asynchronous Processing

A common anti-pattern is submitting tasks to an executor from the listener and returning immediately:

```java
@KafkaListener(topics = "orders", groupId = "order-worker")
public void onOrder(OrderEvent event) {
    executor.submit(() -> orderService.apply(event));
}
```

The container may treat the listener as complete and commit the offset while the task is still running. A later event's task can finish before an earlier event's task. If the task fails, the container also never receives the exception to retry the record properly.

If async processing is required, use one of these approaches:

- Await future completion inside the listener so exceptions propagate back to the container; this still preserves sequential order on the consumer thread.
- Use a per-partition/per-key executor to serialize work sharing the same ordering key.
- Use a worker queue with offset checkpointing, committing contiguously only up to safely completed offsets.
- Route events into a dedicated workflow equipped with version guards and idempotency.

Do not let the listener return before transferring processing and commit responsibility to another durable mechanism. Simply submitting to an in-memory queue risks losing tasks on a process crash even though offsets were already committed.

## 13. Batch Listeners and Ordering on Partial Batch Failure

Batch listeners receive multiple records in a single poll. If the record at index 2 fails, the application can throw `BatchListenerFailedException` with the index so `DefaultErrorHandler` identifies the processed prefix and the record needing retry/recovery.

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-batch-worker",
        containerFactory = "batchListenerFactory")
public void onOrders(List<OrderEvent> events) {
    for (int i = 0; i < events.size(); i++) {
        try {
            orderService.apply(events.get(i));
        } catch (TransientOrderException ex) {
            throw new BatchListenerFailedException(
                    "Batch failed at index " + i, ex, i);
        }
    }
}
```

When the failing index is specified, the framework can handle preceding offsets and seek/retry from the failing record per partition. If the index is not identified, the fallback may retry the entire batch; already-processed records may be redelivered and require idempotency.

A batch can contain records from multiple partitions. List order is not global order; when handling partial failures, understand per-partition semantics and your error handler. `@RetryableTopic` does not support batch listeners in common versions; do not apply record-listener retry-topic examples to batch listeners without checking version limitations.

## 14. Transactions and Retry After Rollback

With container transactions, a listener failure rolls back the Kafka transaction; offsets are not committed with that transaction. `DefaultAfterRollbackProcessor` can seek back to the failed record and retry after rollback, keeping the unsuccessful record at the head of the partition's processing stream.

After the configured number of attempts, the processor can recover the record (e.g., publish to a DLT) and allow the partition to continue. With a transactional recoverer, publishing to the DLT and committing source offsets can be coordinated inside a transaction when properly configured. Distinguish Kafka transactions from external database/HTTP transactions; a Kafka rollback does not automatically undo side effects already committed in external systems.

`@RetryableTopic` non-blocking retry is incompatible with container transactions in common Spring Kafka setups. If strict ordering and transactions are needed, blocking retry / `AfterRollbackProcessor` is typically used. Verify your exact Spring Kafka version before combining retry topics, batch listeners, and transactions.

## 15. Guarding Order with Aggregate Versions or Sequences

When retry topics cannot be avoided or parallel processing is required, include a monotonically increasing per-aggregate version/sequence in the payload:

```java
public record OrderEvent(
        String orderId,
        long aggregateVersion,
        String eventType,
        String status) {
}
```

Consumers can compare the version against stored state:

```java
public void apply(OrderEvent event) {
    long currentVersion = repository.currentVersion(event.orderId());

    if (event.aggregateVersion() <= currentVersion) {
        return; // duplicate or older event already applied
    }

    if (event.aggregateVersion() != currentVersion + 1) {
        throw new MissingPreviousEventException(
                "Missing previous version for order " + event.orderId());
    }

    repository.applyAndAdvanceVersion(event);
}
```

In this example, older or duplicate versions are ignored; events with a gap are delayed/retried until the preceding version is applied. Updating state and version must be atomic in the database, such as via optimistic locking or conditional update statements. Reading the version and writing separately allows two workers to race and apply updates out of order.

A version guard alone does not solve storing missing events. You need a retry/replay mechanism, gap timeouts, and alerts if a preceding version never arrives. For independent events with no ordering relationship, sequential versions are unnecessary.

## 16. Increasing Partition Count Can Alter Key Ordering

Key-based partitioning usually selects a partition based on a hash of the key and the current partition count. When the partition count increases, the same key may route new records to a different partition while older records remain in the old partition.

For example, before scaling, `order-42` was written to partition 1. After increasing the topic's partitions, the partitioner might send new events for `order-42` to partition 4. Because the two partitions are consumed independently, there is no longer a single ordered stream for that order.

If strict per-key ordering is a long-term requirement, plan partition counts up front, use a stable partitioner with managed migration, or cut over to a new topic/version. When expanding an existing topic, assess keys with in-flight events and do not assume ordering across old and new partitions.

## 17. Choosing a Strategy Based on Business Requirements

| Requirement | Suitable strategy | Trade-off |
|---|---|---|
| Strict ordering per partition/key | Blocking retry with `DefaultErrorHandler` or `DefaultAfterRollbackProcessor` | Partition may be blocked during retries |
| Dependency typically recovers in seconds | Short blocking retry with bounded backoff | Increases latency for trailing records |
| Dependency needs long waits, later events are independent | Retry topics / non-blocking retry | Ordering changes; requires idempotency/version guards |
| Older events can be ignored if newer ones already applied | Retry topics + aggregate version check | Must store versions and handle gaps |
| Poison record makes subsequent events invalid if skipped | Pause/stop partition, alert, and fix/replay | Reduces availability and requires a runbook |
| Failed events can be quarantined and handled later | DLT + gap audit + controlled replay | DLT/replay does not automatically restore order |
| Parallel processing across partitions | Concurrency up to partition count | No global ordering across partitions |

## 18. Testing Ordering with Retries

Do not just test that the final record is processed. Record the order in which business events are applied and verify behavior when the first record fails.

### Testing blocking retry

1. Send three events with the same key to one partition: versions 1, 2, 3.
2. Fail the listener on the first attempt for version 1, then succeed on retry.
3. Record listener completion order.
4. Verify versions 2 and 3 are applied only after version 1.
5. Verify offset commits do not advance past the failed record before processing/recovery.

### Testing non-blocking retry

1. Send versions 1, 2, 3 with the same key to one partition.
2. Fail version 1 so it routes to a retry topic.
3. Verify the original topic can process versions 2 and 3 first.
4. Wait for the retry topic to reprocess version 1.
5. Verify the version guard prevents the older event from overwriting newer state or detects the gap per contract.

### Testing producer ordering

1. Send multiple records with the same key while simulating broker/network errors.
2. Inspect producer idempotence and in-flight request settings.
3. Verify partition offsets reflect the expected send order.
4. Repeat with idempotence disabled and multiple in-flight requests to observe the risk when configuration allows it.

Run integration tests against real Kafka via Testcontainers or Embedded Kafka. Unit tests with mocked listeners can verify classifiers/backoff, but are insufficient to prove partition assignment, offsets, retry topic routing, and actual ordering.

## 19. Observing Ordering in Production

Metrics and logs should answer: which record is blocking a partition, are retries letting later events overtake earlier ones, and are DLTs creating unhandled gaps?

- Consumer lag per partition, not only total topic lag.
- Retry counts, backoff durations, and record processing times.
- Records forwarded to retry topics and DLTs by source topic/partition.
- Original topic, partition, offset, key, and aggregate version in logs.
- Listener start and completion timestamps to detect out-of-order async completions.
- Events skipped due to stale versions and events delayed due to missing prior versions.
- Rebalance counts and time partitions spend without an active consumer.

Do not use order IDs or event IDs as high-cardinality metric labels. Put IDs in structured logs or trace attributes; metrics should use bounded-cardinality labels like topic, partition, exception category, and retry destination.

## 20. Common Misconceptions

| Misconception | Accurate understanding |
|---|---|
| Same key means always processed in order | Same key routes to the same partition; retry topics and async processing can still invert completion order |
| Kafka guarantees topic-wide ordering | Ordering is guaranteed only within each partition |
| Retry always holds later records behind earlier ones | Blocking retry generally preserves order; non-blocking retry can let later records pass |
| A retry topic with the same partition number preserves ordering with the source topic | Partitions of different topics share no unified order |
| DLT plus replay automatically restores order | Late replay can run after newer events; needs version guards or sequenced replay |
| Increasing concurrency makes one partition run faster sequentially | Concurrency parallelizes across partitions; a partition is assigned to only one consumer in a group at a time |
| Submitting a task and returning from the listener preserves order | Tasks can finish out of order and offsets may commit before tasks finish |
| Producer retries cannot invert order | Requires idempotence or an appropriate in-flight request limit |
| Increasing partition count does not affect key ordering | Keys may route to new partitions after expansion |

## Checklist Before Enabling Retries on Ordering-Sensitive Streams

- Determine whether ordering is needed at the partition, key, or aggregate level.
- Producer uses a stable key so related events land in the same partition.
- Producer idempotence and `max.in.flight.requests.per.connection` are compatibly configured.
- Do not process asynchronously and return before work and offsets are safely managed.
- Use blocking retry if trailing records must not overtake a failing record.
- Bound retry counts and backoff to avoid infinite head-of-line blocking.
- Use retry topics only when ordering shifts are acceptable or version/sequence guards are in place.
- DLT/replay includes source metadata and a clear gap-handling procedure.
- Check batch listener, transaction, and Spring Kafka version constraints before picking a retry mechanism.
- Test first-event failure, trailing-event success, late retry success, and DLT replay.
- Monitor per-partition lag, retry duration, DLT volume, and aggregate version gaps.
- Assess the impact of increasing partition counts or changing partitioners.

Retry and partition ordering represent a trade-off between strict order and consumption continuity. Blocking retry holds failed records at the head of the stream and preserves in-partition order, but can stall the partition. Retry topics keep the original partition moving while allowing later events to be processed first. Choose according to the business relationship between events, combine with idempotency/version guards, and test actual completion order rather than checking offset order alone.

# Sync Commit and Async Commit

A Kafka consumer must persist offsets to determine where to resume reading after a process restarts or a consumer group rebalances. There are two common ways to commit: **synchronous commit** with `commitSync()` and **asynchronous commit** with `commitAsync()`. Both store the consumer group's offsets on the Kafka broker, but they differ in blocking behavior, how errors are surfaced, and how multiple commits coordinate.

In Spring Kafka, the listener container normally manages commits according to `AckMode`. The container can use `commitSync()` or `commitAsync()` depending on the `syncCommits` setting. Understanding the behavior of the Kafka Consumer API lets operators pick the right mode for throughput, latency, and data safety.

## 1. Committed Offset Is the Next Position to Read

Every record in a partition has a monotonically increasing offset. When a consumer processes the record at offset 41 successfully, the offset to commit is normally **42**—the next position to read. The committed offset is not the last processed record's offset; it is the position to resume consumption from.

Example:

    Partition orders-0

    Offset:       40       41       42       43
                  |        |        |        |
    Record:       A        B        C        D

    Consumer processes A and B successfully
    Commit offset = 42
    Restart -> resume reading from offset 42 (record C)

Kafka can have offset gaps due to compaction, transactions, or records invisible to `read_committed` consumers. Therefore, an offset is not a count of processed records. When committing a specific record, use that record's offset plus one following the next-position convention.

Committing an offset is separate from business processing. If a consumer commits before the database or side effects finish, records can be skipped after a restart. If business processing succeeds but the commit has not finished, records can be redelivered. That is why systems typically choose at-least-once delivery and make consumers idempotent.

## 2. Disable Auto-Commit When Commit Timing Must Be Controlled

The Kafka consumer has an `enable.auto.commit` property. When enabled, the client commits offsets automatically on a schedule, not necessarily synchronized with when the application finishes processing records.

Risk example:

1. The consumer polls a batch containing records 100 through 109.
2. The consumer begins processing record 100.
3. Auto-commit persists offset 110.
4. The application stops when only part of the batch has been processed.
5. After restart, the consumer resumes from 110 and the remaining records in the batch may be skipped.

For business processing requiring tight control, disable auto-commit and let the application or Spring Kafka container commit after successful processing:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
~~~

When using the Kafka Consumer API directly:

~~~java
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
~~~

Disabling auto-commit does not automatically guarantee safe processing. The application must still choose the right commit timing, monitor commit failures, and handle potential duplicates. In Spring Kafka, the listener container normally disables auto-commit when managing offsets itself; configuring it explicitly avoids depending on defaults or other environment overrides.

## 3. Synchronous Commit with commitSync()

`commitSync()` sends an offset commit request and blocks the calling thread until the commit completes or an unrecoverable error is thrown. It is a straightforward way to know the commit result before proceeding.

Common API forms:

~~~java
consumer.commitSync();

consumer.commitSync(Duration.ofSeconds(10));

consumer.commitSync(offsets);

consumer.commitSync(offsets, Duration.ofSeconds(10));
~~~

Passing no map commits the current positions of assigned partitions. Passing a map lets you specify exact offsets per `TopicPartition`. The `Duration` overloads set a timeout limit for the commit operation.

Example of processing the entire batch before committing:

~~~java
while (running) {
    ConsumerRecords<String, OrderEvent> records =
            consumer.poll(Duration.ofMillis(500));

    for (ConsumerRecord<String, OrderEvent> record : records) {
        orderService.process(record.value());
    }

    // Commit only after the entire batch has processed successfully.
    consumer.commitSync();
}
~~~

In this example, if a record throws an exception, the loop does not reach `commitSync()`. Unprocessed records can be redelivered once the consumer recovers. Records processed prior to the error may also be redelivered; the consumer needs idempotency to avoid repeating side effects.

### 3.1. Benefits and Costs of commitSync()

The primary benefit is that the processing flow knows whether the commit succeeded or failed before continuing. For transient, retryable errors, the Kafka client can retry `commitSync()` until it succeeds or times out; unrecoverable errors are thrown to the application.

The drawback is that the thread is blocked while the broker processes the commit. When committing frequently, this latency can reduce throughput and affect poll cadence. When the broker or coordinator is slow, the consumer spends significant time waiting on commits instead of processing records.

`commitSync()` is suitable when:

- You must know the commit outcome for certain before proceeding to a critical step.
- Shutting down the consumer or needing to flush final offsets.
- Handling a partition rebalance and needing to commit safe offsets before relinquishing partitions.
- Load is not overly latency-sensitive and simplicity matters more than squeezing commit throughput.

Do not call `commitSync()` from an arbitrary thread. `KafkaConsumer` is not thread-safe; consumer operations must be coordinated on the thread owning the consumer. In Spring Kafka, letting the container perform commits via `AckMode` is usually safer and more consistent than calling the consumer API directly from a listener.

### 3.2. Committing Specific Offsets

When only part of a batch has been processed, no-arg `commitSync()` can commit the consumer's current position, which has already advanced to the end of the polled data. That can skip unprocessed records. Pass a map containing only safely processed offsets instead.

Example of processing one record and committing right after side effects succeed:

~~~java
TopicPartition partition =
        new TopicPartition(record.topic(), record.partition());

long nextOffset = record.offset() + 1;

Map<TopicPartition, OffsetAndMetadata> offsets = Map.of(
        partition,
        new OffsetAndMetadata(nextOffset)
);

orderService.process(record.value());
consumer.commitSync(offsets, Duration.ofSeconds(10));
~~~

Ordering matters: update and commit the offset only after `orderService.process()` finishes successfully. If `process()` fails, do not commit.

With multiple records in the same partition, commit only up to the highest contiguous position where every prior record succeeded. Never commit a higher offset past a failed record, because Kafka will resume from the committed offset and skip that unprocessed record.

## 4. Asynchronous Commit with commitAsync()

`commitAsync()` sends a commit request and returns immediately without blocking the thread waiting for broker confirmation. Results are delivered via `OffsetCommitCallback`.

Example:

~~~java
consumer.commitAsync((offsets, exception) -> {
    if (exception != null) {
        log.error("Offset commit failed: {}", offsets, exception);
        return;
    }

    log.debug("Offset commit succeeded: {}", offsets);
});
~~~

You can pass a specific offset map:

~~~java
consumer.commitAsync(offsets, (committedOffsets, exception) -> {
    if (exception != null) {
        log.error("Async commit failed: {}", committedOffsets, exception);
    }
});
~~~

The callback receives the requested offset map and an exception if the operation failed. On success, the exception is null. Callbacks let you log, emit metrics, and raise alerts without blocking the main loop waiting for a response.

### 4.1. Benefits and Limitations

`commitAsync()` reduces wait time in the poll loop and is generally suitable for periodic commits in high-throughput consumption pipelines. The application can keep processing after sending the commit request.

However, `commitAsync()` does not automatically retry when a commit fails. The application receives the error in the callback and must decide how to handle it. A failed commit can also leave an uncertain state: the broker may have applied the commit while the response was lost in transit.

Do not blindly re-send every failed commit without considering order. Suppose committing offset 120 fails, and later committing offset 150 succeeds. If the application subsequently retries the stale 120 request, the committed offset could regress to 120 and cause the consumer to re-read more records. That is one reason the Kafka client does not automatically retry `commitAsync()` like `commitSync()`.

### 4.2. Callbacks Must Be Lightweight and Non-Blocking

Callbacks should perform brief work such as logging, incrementing a counter, or updating observable state. Avoid calling remote services, waiting on a database, or doing heavy processing inside the callback. In the Kafka Consumer API, callbacks execute on the consumer's control thread; blocking work can stall the poll loop.

Do not call `commitAsync()` recursively from the callback to retry immediately. If application-level retries are desired, you need sequencing rules, latest-offset checks, and guarantees that an older commit cannot overwrite newer progress. In many systems, logging the error and relying on `commitSync()` at shutdown or an appropriate synchronization point is simpler and safer.

## 5. Comparing commitSync() and commitAsync()

| Criterion | commitSync() | commitAsync() |
|---|---|---|
| Behavior | Waits for commit result | Sends request and continues |
| Thread impact | Blocks calling thread | Does not wait on broker in the call |
| Error delivery | Exception is thrown | Exception is passed via callback |
| Default retry | Retries recoverable errors until success or timeout | Does not automatically retry |
| Poll loop latency | Can increase due to waiting on commit | Typically lower |
| Complexity | Easier to reason about | Requires managing callbacks and ordering |
| Best suited for | Shutdown, rebalance, commits needing confirmation | Periodic commits in high-throughput pipelines |

Both methods can be combined. A common pattern is using `commitAsync()` after successfully processed batches to cut wait time, and then using `commitSync()` at controlled termination points to ensure final offsets are committed before closing the consumer.

## 6. Pattern Combining Async in the Loop and Sync on Shutdown

The pattern below illustrates a consumer processing batches successfully and sending async commits. On controlled shutdown, the consumer performs a final sync commit before closing.

~~~java
try {
    while (running) {
        ConsumerRecords<String, OrderEvent> records =
                consumer.poll(Duration.ofMillis(500));

        for (ConsumerRecord<String, OrderEvent> record : records) {
            orderService.process(record.value());
        }

        consumer.commitAsync((offsets, exception) -> {
            if (exception != null) {
                log.error("Async offset commit failed", exception);
            }
        });
    }
}
finally {
    try {
        // Safe only if every record in the final batch has been processed.
        consumer.commitSync(Duration.ofSeconds(10));
    }
    finally {
        consumer.close();
    }
}
~~~

A critical condition of this example is that the loop calls `commitAsync()` only after processing the entire batch successfully, and normal exit occurs only at a completed batch boundary. If record processing can stop mid-batch, do not call no-arg `commitSync()` in `finally` because it can commit a poll position that has already moved past unprocessed records.

For applications that need to handle mid-batch errors, track safe offsets per partition and use the map-accepting overload. On shutdown, commit only the map of contiguously processed offsets. If no safe offsets remain, skip the final commit and let Kafka redeliver records after restart.

## 7. Tracking Safe Offsets per Partition

A single poll can return records from multiple partitions. Each partition has its own progress. When a record is processed successfully, the application can record the next offset for that partition. This map must advance only after the record's side effects complete.

Example:

~~~java
Map<TopicPartition, OffsetAndMetadata> safeOffsets =
        new HashMap<>();

for (ConsumerRecord<String, OrderEvent> record : records) {
    orderService.process(record.value());

    TopicPartition partition =
            new TopicPartition(record.topic(), record.partition());

    safeOffsets.put(
        partition,
        new OffsetAndMetadata(record.offset() + 1)
    );
}

if (!safeOffsets.isEmpty()) {
    consumer.commitAsync(
        new HashMap<>(safeOffsets),
        (offsets, exception) -> {
            if (exception != null) {
                log.error("Commit failed for {}", offsets, exception);
            }
        }
    );
}
~~~

The example above assumes the loop stops immediately when a record fails and does not continue processing later records in the same partition. If an application processes multiple records from the same partition in parallel, it must track the result set and commit only the offset after the last contiguously completed record. You cannot simply take the highest offset among completed tasks.

Illustration:

    Partition orders-0

    Offset:       10       11       12       13
    Result:       OK       FAIL     OK       OK

    Offset 10 processed
    Offset 11 not processed successfully
    Offsets 12 and 13 finished, but cannot commit past 11

    Safe offset to commit = 11

Committing 14 would make the consumer start at 14 upon restart and skip record 11. With parallel processing, you need per-record state tracking and contiguous watermark calculation per partition.

## 8. Rebalances and Final Commits Before Relinquishing Partitions

A consumer group can rebalance when consumers join/leave the group, hit session timeout, exceed max poll interval, or when partition count changes. When partitions are about to be revoked, the consumer should commit successfully processed offsets before giving up ownership.

With the Kafka Consumer API, `ConsumerRebalanceListener` can be used:

~~~java
consumer.subscribe(
    List.of("orders"),
    new ConsumerRebalanceListener() {
        @Override
        public void onPartitionsRevoked(
                Collection<TopicPartition> partitions) {

            Map<TopicPartition, OffsetAndMetadata> offsets =
                    processedOffsetsFor(partitions);

            if (!offsets.isEmpty()) {
                consumer.commitSync(offsets, Duration.ofSeconds(10));
            }
        }

        @Override
        public void onPartitionsAssigned(
                Collection<TopicPartition> partitions) {
            // Initialize processing state for new partitions.
        }
    }
);
~~~

`processedOffsetsFor()` is an application-implemented method returning safely processed next offsets only for the partitions about to be revoked. Do not commit the entire current position if unprocessed records remain.

Some Kafka versions provide an `onPartitionsLost()` callback to signal that partition ownership has already been lost. When partitions are lost, the consumer can no longer reliably commit offsets for those partitions; do not attempt to commit as if ownership still held. Handle partition loss and let the new consumer resume from the last committed offset.

In Spring Kafka, the listener container manages rebalances and offset commits. Do not call `KafkaConsumer.commitSync()` yourself from an arbitrary listener callback; use `AckMode`, `Acknowledgment`, and container hooks suited to your library version.

## 9. Spring Kafka: Does the Container Commit Synchronously or Asynchronously?

The Spring Kafka listener container manages offset commits after the listener finishes according to `AckMode`. `ContainerProperties.syncCommits` controls how the container sends commits:

- `syncCommits=true`: the container uses `commitSync()`. This is the common default.
- `syncCommits=false`: the container uses `commitAsync()` and can invoke a commit callback to report results.

Listener container configuration example:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
kafkaListenerContainerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);

    ContainerProperties properties = factory.getContainerProperties();
    properties.setAckMode(ContainerProperties.AckMode.RECORD);
    properties.setSyncCommits(true);
    properties.setSyncCommitTimeout(Duration.ofSeconds(10));

    return factory;
}
~~~

With `RECORD`, the container commits the offset after each record is processed successfully by the listener. With `BATCH`, the container commits after the entire batch returned from a poll is processed successfully. Actual committing still depends on container settings and active transactions.

To use async commits:

~~~java
ContainerProperties properties = factory.getContainerProperties();

properties.setAckMode(ContainerProperties.AckMode.RECORD);
properties.setSyncCommits(false);
properties.setCommitCallback((offsets, exception) -> {
    if (exception != null) {
        log.error("Spring Kafka async commit failed: {}", offsets, exception);
    }
    else {
        log.debug("Spring Kafka async commit succeeded: {}", offsets);
    }
});
~~~

The commit callback receives the offsets the container requested to commit and an exception if the commit failed. Keep callbacks short and avoid blocking work. If the callback only logs without alerts or metrics, commit failures can go unnoticed in operations.

API names and signatures can vary across Spring Kafka versions. Verify actual dependencies before applying configuration or imports.

## 10. AckMode and Manual Acknowledgment

`AckMode` determines when the Spring Kafka container considers records ready to commit. Common modes:

| AckMode | Commit Timing |
|---|---|
| `RECORD` | After the listener successfully processes each record |
| `BATCH` | After all records in the poll batch succeed |
| `TIME` | When the configured time duration has elapsed and processing conditions are met |
| `COUNT` | When the configured number of processed records is reached |
| `COUNT_TIME` | When either the count or time threshold is reached |
| `MANUAL` | Listener calls `acknowledge()`; container commits at the batch boundary |
| `MANUAL_IMMEDIATE` | Listener calls `acknowledge()`; container commits immediately if called on the consumer thread |

`MANUAL` and `MANUAL_IMMEDIATE` both require explicit listener acknowledgment. The difference is when the container applies the acknowledgment. With `MANUAL_IMMEDIATE`, calling `acknowledge()` on the consumer thread lets the container commit right away; when called from another thread, the acknowledgment is routed back to the container thread and no longer carries the same "immediate" meaning. Do not mix consumer-thread and off-thread calls within the same listener without understanding container processing order.

Manual acknowledgment example:

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void consume(
        ConsumerRecord<String, OrderEvent> record,
        Acknowledgment acknowledgment) {

    orderService.process(record.value());

    // Acknowledge only after business processing succeeds.
    acknowledgment.acknowledge();
}
~~~

You can select `MANUAL_IMMEDIATE` and have the container use sync commits:

~~~java
ContainerProperties properties = factory.getContainerProperties();
properties.setAckMode(ContainerProperties.AckMode.MANUAL_IMMEDIATE);
properties.setSyncCommits(true);
~~~

If switching to `syncCommits=false`, the acknowledgment will be committed through the container's async path. The listener does not receive the commit result immediately upon calling `acknowledge()`; monitor the container's commit callback and design retry/idempotency for failed commits or ambiguous responses.

## 11. Relationship Between Database Transactions and Offset Commits

A consumer typically executes database side effects before committing Kafka offsets. This ordering avoids marking a record complete before business data is durably persisted.

    Poll record
       |
       v
    Begin database transaction
       |
       v
    Update business data
       |
       v
    Database commit
       |
       v
    Kafka offset commit

If the application stops after the database commit but before the offset commit, Kafka redelivers the record. This produces a duplicate on the next processing attempt. The consumer should use `eventId` and an `inbox`/`processed_event` table within the same database transaction as the business update.

If the offset is committed before the database commit and the database then rolls back, the record may be skipped. Therefore, never commit before side effects are durable unless the business accepts at-most-once semantics.

Kafka transactions can combine writing output records and consumer offsets within the same Kafka transaction. They do not automatically create an atomic transaction with an independent database. For flows writing to a database and publishing Kafka events, consider Transactional Outbox; for flows consuming from Kafka and writing to a database, consider Inbox or idempotent updates.

## 12. Timeouts, Polling, and Commit Failures

Commits take time to communicate with the group coordinator. When the coordinator is unavailable, the network is slow, or the group is rebalancing, commits can fail or time out.

Settings and conditions to examine:

- `request.timeout.ms`: time to wait for a response to a single request.
- `default.api.timeout.ms`: default limit for APIs with timeouts.
- `max.poll.interval.ms`: time limit between polls before a consumer may be considered stalled.
- `session.timeout.ms` and `heartbeat.interval.ms`: affect detection of disconnected consumers.
- Spring Kafka's `syncCommitTimeout`: synchronous commit wait timeout used by the container.

Do not increase timeouts mechanically to hide consumers that process too slowly. If a listener takes longer than `max.poll.interval.ms` to process a batch, the group may rebalance and the old consumer's commit may fail. Check processing duration, records per poll, concurrency, and batch splitting.

When a commit fails:

1. Record the consumer group, topic, partition, and offset requested for commit.
2. Classify the error: timeout, coordinator unavailable, rebalance, authorization, or configuration error.
3. Determine how far business processing progressed.
4. Do not assume a failed commit means the broker definitely did not persist the offset.
5. Allow records to be redelivered and rely on idempotency when commit state is uncertain.

## 13. Observing Commits in Production

Monitor both record-processing activity and offset-commit activity:

**Commit metrics**

- Count of `commitSync` and `commitAsync` calls.
- Commit success/failure rate.
- Commit latency and timeout count.
- Exceptions by category: rebalance, coordinator, network, authorization.
- Requested commit offsets by topic and partition.

**Consumer metrics**

- Consumer lag by group and partition.
- Poll rate and record processing rate.
- Batch and per-record processing duration.
- Rebalance count and revoked/lost partitions.
- Count of redelivered or duplicate-handled records.

**Logs and traces**

Commit logs should include group ID, topic, partition, offset, commit mode, and error cause. Correlate `eventId` with business logs to determine whether a record was processed prior to commit. Avoid logging only a generic "commit failed" message without the relevant offsets.

Low consumer lag alone does not prove zero message loss. Offsets could have been committed prematurely before side effects completed. Cross-check offsets against business outcomes, input event counts, and processing states.

## 14. Testing Commit Behavior

In test environments, simulate critical failure windows:

1. Consumer finishes processing a record and stops before commit: the record may be redelivered, yet side effects must not duplicate.
2. Consumer stops mid-batch: the offset must not advance past unprocessed records.
3. Broker coordinator is temporarily unavailable: `commitSync` must report an error or time out; `commitAsync` must invoke its callback with an error when the request fails.
4. An async commit fails followed by a newer successful commit: do not blindly retry the old offset and regress progress.
5. Consumer rebalances during processing: commit only safe offsets for partitions about to be yielded.
6. Commit callback encounters an error: metrics and logs must capture group, partition, offset, and exception.
7. Listener commits database changes successfully but offset commit fails: redelivery must remain safe via idempotency.
8. Controlled application shutdown: final commit includes only completely processed offsets.

These tests verify the commit policy under real failure behaviors, especially at moments when the application and broker can lose connectivity.

## 15. Choosing a Commit Mode by Scenario

| Scenario | Appropriate Choice |
|---|---|
| Moderate-load consumer needing simplicity and known commit results | `commitSync()` |
| Continuous consumer with periodic commits and latency sensitivity | `commitAsync()` with callback and error monitoring |
| Consumer undergoing controlled shutdown | `commitSync()` for final safely processed offsets |
| Partitions about to be revoked during rebalance | `commitSync` with map of processed offsets for revoked partitions |
| Success tracked per individual record in Spring Kafka | `AckMode.RECORD` |
| Batch processing in Spring Kafka | `AckMode.BATCH` |
| Listener needs to acknowledge explicitly after side effects | `MANUAL` or `MANUAL_IMMEDIATE` |
| Listener needs callback on async commit errors | `syncCommits=false` and commit callback |
| Parallel processing within the same partition | Commit only the contiguous watermark of completed records |

Sync commits and async commits are two ways to persist progress for the same consumer group. Sync commits suit points where waiting for the outcome and synchronizing state matter; async commits cut waiting inside the poll loop but require callbacks, error monitoring, and ordering discipline. Whichever mode you choose, commit offsets only after preceding records have processed successfully, allow redelivery when outcomes are uncertain, and design idempotent side effects so consumers recover safely.
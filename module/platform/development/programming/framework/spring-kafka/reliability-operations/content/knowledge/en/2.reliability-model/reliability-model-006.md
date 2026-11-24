# Offsets as a Progress Checkpoint

In Kafka, a consumer reads data from a topic partition by partition. An offset is the sequential number of a position within that partition. When a consumer processes a record and commits an offset, it records the checkpoint from which the consumer group can resume reading after a restart or after receiving partitions from another consumer.

Therefore, offsets are an essential part of reliability: they help Kafka and the application determine how far reading progress has been recorded. However, an offset only reflects progress committed by the consumer. By itself, it does not prove that a database operation or an external system call completed safely. To operate properly, you must understand the difference between read position, processed records, acknowledgements, and committed offsets.

## 1. Offsets Are Defined per Partition

A topic can be split into multiple partitions. Kafka assigns offsets to records within each partition in ascending order. For example, topic `orders` has two partitions:

| Partition | Example offsets |
|---|---|
| `orders-0` | 0, 1, 2, 3, 4, ... |
| `orders-1` | 0, 1, 2, 3, 4, ... |

Offset `3` in partition 0 and offset `3` in partition 1 are two different records. Thus, a record is uniquely identified by the tuple of topic, partition, and offset; looking at the offset alone is insufficient.

Ordering is guaranteed within a single partition. Kafka does not provide a global offset sequence to strictly order every record across all partitions of a topic. If the application requires ordering for events of the same entity, the producer typically selects a suitable key so those events are written to the same partition.

Offsets should also not be interpreted as the count of processed records. A compacted topic may drop older records while keeping the offsets of remaining records intact; certain control records in the log can also leave gaps in the observed offset sequence. Hence, seeing an offset jump from `10` to `13` does not necessarily mean the application skipped two records.

## 2. Three Concepts to Distinguish

When tracking progress, distinguish the current read position, the committed offset, and the end of the log.

| Concept | Meaning | Lifecycle |
|---|---|---|
| Consumer position | The next position the consumer will read in a partition. This position advances as records are returned from `poll()`. | Runtime state inside the consumer; can be lost when the consumer stops. |
| Committed offset | The saved resume checkpoint for a consumer group and partition. The committed value is typically the next offset to read. | Stored by Kafka so the consumer can recover after restarts or rebalances. |
| Log end offset | The position at the tail of a partition's log, i.e., the next offset after existing log entries. | Advances as producers append more data. |

The easiest point to confuse is that the committed offset usually represents **the next offset to read**, rather than the offset of the last processed record. If the record at offset `41` was processed successfully and the consumer commits `42`, the next read will begin at offset `42`.

Kafka stores committed offsets per consumer group and partition in the internal `__consumer_offsets` topic. Two different consumer groups can read the same topic while maintaining independent progress checkpoints. Within a single group, each partition has its own committed offset.

## 3. How Does an Offset Become a Progress Checkpoint?

The typical processing flow can be visualized as follows:

```text
Kafka partition
      |
      v
consumer poll() --------> consumer position advances
      |
      v
Spring Kafka listener processes record
      |
      v
listener succeeds / acknowledgment
      |
      v
container commits offset
      |
      v
Kafka stores committed offset for group and partition
```

`poll()` delivers records to the consumer and advances the consumer position. That does not mean business logic has finished. In Spring Kafka, the listener container coordinates when acknowledgement and commits occur based on `AckMode` and related settings. Once the offset is committed, Kafka has a recovery checkpoint that the consumer group can use on subsequent reads.

For example, consumer group `order-processor` is reading partition `orders-0`:

| Event | Record offset | Committed offset after event |
|---|---:|---:|
| Start reading | 50 | 50 |
| First record processed successfully | 50 | 51 |
| Next record processed successfully | 51 | 52 |
| Start processing next record | 52 | 52 |

Here, committed offset `52` indicates the consumer can resume from the record at offset `52`. It does not mean the record at offset `52` has already been processed.

Acknowledgement and commit are related, though not always the exact same operation. With automatic container modes, returning normally from the listener tells the container the record is processed; the container commits according to `AckMode`. With manual modes, the listener calls `Acknowledgment.acknowledge()` to inform the container that the record or batch is acknowledged. Actual commit timing still depends on which manual mode is used and the processing status of records in the current poll.

## 4. Choosing Commit Timing in Spring Kafka

Spring Kafka provides `ContainerProperties.AckMode` to define how the listener container records progress. For listener containers, `enable.auto.commit` defaults to `false` starting in Spring Kafka 2.3 if the application has not configured it. Configure it explicitly to avoid confusion with the Kafka client's auto-commit mechanism.

Common modes:

| AckMode | When does the container commit? | When appropriate |
|---|---|---|
| `RECORD` | After each record is successfully processed by the listener. | Wanting the commit checkpoint to track each record closely; only for record listeners. |
| `BATCH` | After all records returned from a single `poll()` are successfully processed. This is the listener container default. | Wanting fewer commits and accepting poll-batch progress checkpoints. |
| `TIME` | When pending acknowledgements exist and the `ackTime` interval since the previous commit has elapsed. | Throttling commits by time interval. |
| `COUNT` | When the number of records since the previous commit reaches `ackCount`. | Throttling commits by record volume. |
| `COUNT_TIME` | When either the time or count threshold is met, whichever comes first. | Combining time and record-count limits. |
| `MANUAL` | Listener explicitly calls `acknowledge()`; offsets are queued and committed at poll processing boundaries, similar to `BATCH`. | Application needs to decide which records are acknowledged. |
| `MANUAL_IMMEDIATE` | When the listener calls `acknowledge()` on the consumer thread, the container requests an immediate commit; if called from another thread, the acknowledgement is queued. | Needing an immediate commit request upon acknowledgement and clear control over the calling thread. |

Example record listener configuration with Spring Boot:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-processor
      enable-auto-commit: false
    listener:
      ack-mode: record
```

The listener can accept `ConsumerRecord` to access record metadata:

```java
@KafkaListener(topics = "orders")
public void consume(ConsumerRecord<String, OrderCreated> record) {
    orderService.handle(record.value());

    log.info(
        "Processed topic={}, partition={}, offset={}",
        record.topic(),
        record.partition(),
        record.offset()
    );
}
```

With `AckMode.RECORD`, when `orderService.handle()` completes normally, the container can commit progress for that record. If the method throws an exception, the container delegates error handling to the error handler; the record can be retried or recovered according to the configured policy. Do not catch and ignore an exception if the business work is not actually finished, because the container may interpret the listener as successful and commit progress anyway.

If manual acknowledgement is needed, configure `MANUAL` and accept an `Acknowledgment` parameter:

```yaml
spring:
  kafka:
    listener:
      ack-mode: manual
```

```java
@KafkaListener(topics = "orders")
public void consume(
        ConsumerRecord<String, OrderCreated> record,
        Acknowledgment acknowledgment) {

    orderService.handle(record.value());
    acknowledgment.acknowledge();
}
```

The `acknowledge()` call should come after the work requiring protection has completed. If `orderService.handle()` writes to a database, ensure the database transaction has succeeded before acknowledging the record. With `MANUAL`, calling acknowledge marks the record as acknowledged; the container commits per manual mode rules once related records in the poll are processed.

Do not hand off a record to an executor and let the listener return immediately while background work is still running. The container may consider the listener done and commit the offset before the work actually completes. If asynchronous processing is required, use the async listener/acknowledgement mechanisms supported by your Spring Kafka version and acknowledge only when processing completes. For acknowledgements off the consumer thread or out-of-order completion, carefully check the `asyncAcks` setting and the limits of your Spring Kafka version.

## 5. What Does the Offset Determine When the Application Fails?

The committed offset is the recovery checkpoint after a failure. Consider a consumer processing the record at offset `80` and writing data to a database.

**Process first, commit after:**

1. Listener receives record `80`.
2. Application writes changes to the database successfully.
3. Application stops before committing offset `81`.
4. Consumer restarts and reads again from committed offset `80`.
5. The same business operation may be executed a second time.

This is a situation that can cause duplicate processing. This approach generally supports **at-least-once delivery**: records are not skipped merely because the application stopped between processing and committing, though a record may be redelivered.

**Commit first, process after:**

1. Consumer commits offset `81`.
2. Application stops before writing changes to the database.
3. Consumer restarts from offset `81`.
4. Record `80` is not read again given the committed progress, so business work may be lost.

This is the risk of **at-most-once processing**: it reduces the chance of duplicate processing, but work can be lost if a failure occurs after the commit and before processing completes.

Therefore, for critical business logic, the standard order is to finish processing successfully before confirming the offset, while making business operations idempotent. For example, the application can use an event ID as a unique key, maintain a processed inbox table, or use database unique constraints so redeliveries produce no additional business effects. Idempotency handles the case where a record is delivered multiple times; committing offsets helps the consumer recover its read position.

Kafka transactions can provide exactly-once semantics for flows reading from Kafka and writing results back to Kafka: output records and input offsets are committed in the same transaction. Consumers reading transactional data typically use isolation level `read_committed` so they do not receive results from aborted transactions. This mechanism does not automatically make writes to an external database exactly-once. For systems combining Kafka and a database, additional design such as inbox/outbox, idempotency keys, or a suitable transaction coordination workflow is required.

## 6. Retries, Recovery, and Rebalancing

When a listener throws an exception, the Spring Kafka error handler decides what happens next: retry in place, wait for backoff, seek to reread, move the record to recovery, or apply another policy. Therefore, you cannot see a listener throw an exception and assume with certainty that the committed offset will remain unchanged. Check the active error handler and recovery configuration. A successfully recovered record may be considered processed per container and error handler policy.

When a consumer group rebalances, Kafka may reassign partitions from one consumer to another. The new consumer resumes from the group's committed offset for that partition. Processed-but-uncommitted records can be redelivered; that is why idempotent processing remains essential even when listeners run smoothly under normal conditions.

The `auto.offset.reset` property is also often misunderstood. This property is used when a group has no valid committed offset for a partition or the stored offset is no longer valid, for instance because old data expired past retention. Common options are:

- `earliest`: start from the earliest offset still readable.
- `latest`: start from new data at the tail of the partition.
- `none`: throw an error if no valid offset exists.

`auto.offset.reset` does not reset a valid committed offset every time the application starts. To replay data, explicitly reset the consumer group's offsets using an appropriate administrative tool or use a new group ID, after evaluating the impact of reprocessing.

## 7. Using Offsets to Observe Lag

Consumer lag is typically approximated as the difference between the log end offset and the committed offset of each partition:

```text
lag(partition) = log end offset - committed offset
```

For example, if the log end offset is `1,250` and the committed offset is `1,200`, the offset lag is roughly `50`. This is an indicator of how many offset positions behind the log the consumer group sits. Because the log can contain gaps, this number does not always equal the exact count of business records waiting to be processed.

When monitoring the system, observe lag per partition and over time. Steadily rising lag can indicate processing speed is lower than producer write rate, partition skew, a slow listener, or prolonged retries. Lag dropping to 0 shows the committed offset has caught up with the end of the log at measurement time, yet does not by itself prove all external effects are durable if the application committed too early.

Alongside lag, monitor commit rate, record processing duration, retry counts, listener errors, rebalance counts, and load distribution across partitions. When investigating a specific record, log `topic`, `partition`, `offset`, and event ID so you can correlate application traces with positions in Kafka.

## 8. Operational Principles to Maintain

- Treat offsets as resume checkpoints per consumer group and partition; do not treat them as global sequence numbers.
- Disable Kafka client auto-commit when letting the Spring Kafka listener container manage acknowledgement and commits; configure `enable-auto-commit=false` explicitly.
- Choose `AckMode` based on commit latency, throughput, and replay requirements. `RECORD` gives finer progress checkpoints; `BATCH` reduces commit frequency by grouping per poll.
- Acknowledge only after the protected work is complete. Be especially careful with asynchronous work and caught-and-ignored exceptions.
- Design business logic idempotently to tolerate records redelivered after crashes, retries, or rebalances.
- Monitor committed offsets and lag per partition; inspect the error handler before concluding whether a failed record will be retried or recovered.
- Resetting offsets is an operational action that directly affects which data is reread or skipped. Verify the exact group, topic, partition, and target position before executing it.

Offsets allow consumer groups to remember reading progress and recover after failures. The reliability of the overall workflow depends on the application choosing the right confirmation timing, handling errors consistently, and protecting business operations against the possibility that a record is redelivered.

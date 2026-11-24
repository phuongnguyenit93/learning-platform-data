# Meaning of Offsets in a Partition

In Kafka, each record written to a partition has a position called an **offset**. The offset indicates the position of the record within that partition's log, helping consumers track where they are reading from and resume from the saved position after a restart. Offsets are also important for tracing records, checking consumer lag, replaying data, and determining processing progress.

An offset is meaningful only within the scope of a single partition. It is not a global identifier for a record, not a shared sequence number across an entire topic, and does not necessarily reflect the number of records processed. To identify a record in Kafka, you must combine the topic name, partition, and offset.

## 1. An Offset Is a Position in a Partition's Log

A topic is divided into one or more partitions. Each partition is an independent log to which records are appended at the end. The broker assigns an offset to each record when writing to the partition. The offset increases as writes progress in that partition.

For example, the `orders` topic has two partitions:

```text
orders-0:  offset 0 -> offset 1 -> offset 2 -> offset 3 -> ...
orders-1:  offset 0 -> offset 1 -> offset 2 -> offset 3 -> ...
```

Offset `2` in `orders-0` and offset `2` in `orders-1` are two different records. You cannot identify a record by offset alone while omitting the partition.

A record can be identified by the triplet:

```text
topic     = orders
partition = 0
offset    = 42
```

This is the position of a record in the `orders-0` partition log. When logging, you should store all three fields along with an event ID or business key if cross-system tracing is needed.

## 2. Offsets Are Not Global Sequence Numbers

Kafka only guarantees record ordering within the same partition. Two partitions can be written to and read by consumers independently. Therefore, offset 100 in partition 0 did not necessarily occur before offset 50 in partition 1.

| Scope | Ordering Guarantee |
|---|---|
| Single partition | Records are ordered by increasing offset |
| Multiple partitions in the same topic | No global ordering across partitions |
| Multiple topics | No global ordering guaranteed by Kafka |

If the business logic requires events for the same order to be read in order, the producer typically sends `orderId` as the key so that records with the same key are routed to the same partition. Then the offset within the partition allows the consumer to read the order's events in the order they were written.

Do not use offsets to compare business timing across partitions. If you need timing, use the record timestamp or a business time field in the payload. Timestamps also have their own semantics and do not replace offsets.

## 3. How Are Offsets Assigned?

The producer sends a record to a topic. The partitioner selects the target partition; the partition's leader broker writes the record to the log and assigns an offset. The producer receives response metadata, typically including the topic, partition, and offset of the written record.

Basic flow:

```text
Producer sends record
        |
        v
Select partition
        |
        v
Leader broker appends record to log
        |
        v
Assign offset within partition
        |
        v
Producer receives metadata (partition, offset)
        |
        v
Consumer polls and receives record with offset
```

Example of sending with Spring Kafka:

```java
CompletableFuture<SendResult<String, OrderCreated>> future =
        kafkaTemplate.send("orders", event.orderId(), event);

future.whenComplete((result, error) -> {
    if (error != null) {
        log.error("Failed to send order event", error);
        return;
    }

    RecordMetadata metadata = result.getRecordMetadata();
    log.info("topic={}, partition={}, offset={}",
            metadata.topic(), metadata.partition(), metadata.offset());
});
```

`RecordMetadata.offset()` is the offset of the record acknowledged by the broker. If the producer retries or uses idempotence, the client handles certain resend scenarios within the producer's guarantees; that does not turn the offset into a business event ID. If the application publishes the same event using a new send call, the new record can still have a different offset.

## 4. Offsets Are Not Necessarily Contiguous in Data Received by Consumers

Offsets generally increase monotonically, but consumers should not assume the records they see will always have consecutive offsets 0, 1, 2, 3. Gaps can occur because:

- Topics using log compaction: Kafka may remove older records with the same key without renumbering the offsets of remaining records.
- Consumers using `isolation.level=read_committed`: records belonging to aborted transactions are not returned to the consumer, so the corresponding offsets may be skipped.
- The log contains control records for transactions or internal records that the application does not receive as regular business records.
- Retention deletes old segments; consumers can no longer read offsets that have been deleted.

For example, after compaction, a consumer may see:

```text
Offset 10: key=A, value=A-v1   (compacted out of the readable log)
Offset 11: key=B, value=B-v1
Offset 12: key=A, value=A-v2
Offset 13: key=C, value=C-v1

Consumer may receive: 11, 12, 13
```

The example above illustrates that an offset is a log position, not the element index in the list received by the consumer. Do not increment an offset by counting processed records and assuming the next offset equals that count.

## 5. Key Offset Milestones in a Partition

When operating Kafka, it is often necessary to distinguish log start offset, log end offset, high watermark, and last stable offset. These milestones describe the log range and readable data according to isolation level.

| Milestone | Meaning |
|---|---|
| Log start offset | The earliest offset still readable in the partition; it can increase when retention or compaction removes old data |
| Log end offset (LEO) | The next position at the end of the leader log; a new record will be appended at this position |
| High watermark (HW) | The boundary of data sufficiently replicated according to Kafka semantics; `read_uncommitted` consumers only read data below this boundary |
| Last stable offset (LSO) | The safe reading boundary for `read_committed` consumers; open transactions can hold the LSO behind the HW |

Conceptual illustration:

```text
log start                                      log end
    |                                             |
    v                                             v
    +---- written and replicated data ----+-------+
                          ^               ^
                          |               |
                         HW              LEO

If there is an unfinished transaction:
                         LSO
                          ^
                          |
               read_committed stops here
```

LEO can be ahead of HW because a record has been appended on the leader but not yet sufficiently replicated. With `read_uncommitted`, consumers do not read past the high watermark. With `read_committed`, consumers only receive records from committed transactions and non-transactional data up to the LSO; open transactions can prevent subsequent records from becoming visible yet.

These milestones are offset positions, typically representing the next boundary rather than the offset of the last record. When reading metrics or admin tool output, verify the exact semantics of the displayed fields and Kafka version.

## 6. Log Start Offset Changes on Retention or Compaction

Offsets are not renumbered from 0 after Kafka deletes old data. For example, a partition once had offsets from 0 to 999. After retention, the initial segments are deleted and the log start offset may move up to 400. New records continue to be written with offsets at the end of the log, never returning to offset 0.

```text
Before retention:
0  1  2  3  4  5  ...  999

After retention:
                    400 401 402 ... 999
                    ^
                    log start offset
```

If a consumer group has a committed offset of 250 but the log start offset has increased to 400, the consumer cannot re-read offset 250 because that data has been removed. The client may encounter `OffsetOutOfRangeException`; the `auto.offset.reset` policy determines how to handle an offset that is no longer valid.

`auto.offset.reset=earliest` means starting from the earliest offset still retained, not always returning to offset 0. `latest` starts from the end of the log at the time of the reset. If the group already has a valid committed offset, `auto.offset.reset` is not applied merely because the consumer restarts.

For compacted topics, compaction retains the latest value per key in a background process and can create similar offset gaps. A tombstone is also a record with an offset, used to indicate key deletion; it is not an empty offset.

## 7. Consumer Position and Committed Offset Are Different

A consumer has two important concepts:

- **Position**: the consumer's current position in the partition, i.e., the next offset the consumer will receive on poll.
- **Committed offset**: the position saved for the consumer group so the consumer can resume after a restart or rebalance.

Example where a consumer just received record offset 40:

```text
Record just received:  offset 40
Consumer position:     41 (next expected read position)
Committed offset:      40 or lower (if new progress has not been committed yet)
```

In the example, the committed offset may still be 40 if the group previously saved the starting position at 40; after finishing processing record 40, the consumer needs to commit offset 41. Position can advance when records are returned from `poll()`, even if business processing is not yet complete. Therefore, do not treat the current position as proof that a record has been durably processed.

If the consumer processes record 40 successfully but has not committed 41 before the process stops, the next run may receive record 40 again. This is common at-least-once behavior. If 41 is committed before processing succeeds, stopping the process can cause record 40 to be skipped in the next run.

## 8. Why Is the Committed Offset the Next Position to Read?

Kafka stores the committed offset as the next position the consumer group needs to read, not the offset of the last processed record. If record offset 42 is processed successfully, the position to commit is 43.

```text
Partition orders-0:

offset 40  -> processed
offset 41  -> processed
offset 42  -> just processed successfully
offset 43  -> next position to read

Commit: 43
```

Example of manual commit with the Kafka client:

```java
Map<TopicPartition, OffsetAndMetadata> offsets = new HashMap<>();
TopicPartition partition = new TopicPartition("orders", 0);

// Record offset 42 has been processed successfully, so commit the next position 43.
offsets.put(partition, new OffsetAndMetadata(43));
consumer.commitSync(offsets);
```

If you call `commitSync()` without passing a map, the Kafka client commits the consumer's current positions. Only do this after the corresponding records have been processed successfully. When processing concurrently, ensure you do not commit past the offset of an unfinished record in the same partition.

Spring Kafka also follows the principle of committing the next position. With container-managed AckMode, Spring calculates the offset to commit after the listener finishes according to the selected mode. When using `Acknowledgment`, call `acknowledge()` after business logic completes or the work has been durably persisted.

## 9. Reading Offset Metadata with KafkaConsumer

The Kafka client provides APIs to inspect position, committed offset, and partition milestones. The APIs below should be called on the thread owning the `KafkaConsumer`; consumers are not thread-safe.

```java
TopicPartition tp = new TopicPartition("orders", 0);

// After partitions have been assigned:
long position = consumer.position(tp);

OffsetAndMetadata committed = consumer.committed(tp);
Long committedOffset = committed == null ? null : committed.offset();

Map<TopicPartition, Long> beginning =
        consumer.beginningOffsets(Set.of(tp));
Map<TopicPartition, Long> end =
        consumer.endOffsets(Set.of(tp));

log.info("position={}, committed={}, beginning={}, end={}",
        position, committedOffset, beginning.get(tp), end.get(tp));
```

`position(tp)` returns the next position the consumer will read. `committed(tp)` returns the offset the group has committed or `null` if none exists. `beginningOffsets()` and `endOffsets()` return the log boundaries visible to the consumer client according to its isolation level and cluster state. Calls to fetch offsets may require metadata exchange with the broker; do not call them repeatedly in the per-record processing path.

To move a consumer to a specific offset, you can use `seek()` after the partition has been assigned:

```java
consumer.seek(tp, 100L);
```

`seek()` changes the consumer's local position; it does not automatically commit the new offset for the group. If the consumer restarts before committing, the old committed offset remains the resume point. `seekToBeginning()` and `seekToEnd()` also change the position without automatically changing the saved committed offset.

## 10. Finding Offsets by Timestamp

Kafka stores a timestamp with each record. A consumer can find the first offset whose timestamp is greater than or equal to a requested time using `offsetsForTimes()`:

```java
Map<TopicPartition, Long> timestamps = Map.of(tp, targetEpochMillis);
Map<TopicPartition, OffsetAndTimestamp> matches =
        consumer.offsetsForTimes(timestamps);

OffsetAndTimestamp match = matches.get(tp);
if (match != null) {
    consumer.seek(tp, match.offset());
}
```

If no matching record is found in the partition, the result may be `null`. The timestamp used may be `CreateTime` provided by the producer or `LogAppendTime` assigned by the broker, depending on topic/broker configuration. If you need to replay from a business point in time, you must understand what time the timestamp represents and account for latency between event generation and writing to Kafka.

Finding offsets by timestamp is useful for time-range replays, incident investigation, or rerunning data from a checkpoint. After finding the offset, clearly determine which group is consuming and whether the new position needs to be committed. Do not use `seek()` as a permanent offset reset operation if the consumer group needs to resume from the new position after a restart; when changing the committed offset is needed, use administrative tools or an intentional commit.

## 11. Offsets in Spring Kafka

With `@KafkaListener`, you can receive `ConsumerRecord<K, V>` directly to read record metadata:

```java
@KafkaListener(topics = "orders", groupId = "orders-worker")
public void onOrder(ConsumerRecord<String, OrderCreated> record) {
    log.info("topic={}, partition={}, offset={}, timestamp={}, key={}",
            record.topic(),
            record.partition(),
            record.offset(),
            record.timestamp(),
            record.key());

    orderService.handle(record.value());
}
```

`ConsumerRecord` provides access to topic, partition, offset, timestamp, key, value, and headers. This is a clear approach when you need tracing or per-partition processing. If the listener only receives the payload, Spring Kafka still manages metadata and offsets in the container, but the method lacks the full record details.

With manual acknowledgment:

```java
@KafkaListener(topics = "orders", groupId = "orders-worker")
public void onOrder(
        ConsumerRecord<String, OrderCreated> record,
        Acknowledgment acknowledgment) {

    orderService.handleAndPersist(record.value());
    acknowledgment.acknowledge();
}
```

The container commits the next position after the acknowledged record, according to AckMode and Spring Kafka semantics. Do not take `record.offset()` and commit that exact number yourself; the committed offset must be the next position. Also do not acknowledge before business side effects complete if you want to avoid missed processing.

## 12. Offsets and Consumer Lag

Consumer lag is typically calculated as the difference between the log end offset and the position committed by the consumer group or the tracked read position, depending on the metrics system. Conceptually:

\[
\text{lag} \approx \text{log end offset} - \text{committed offset}
\]

For example, if the log end offset is 500 and the committed offset is 470, the lag is approximately 30 offsets. This is a position difference, not necessarily equal to exactly 30 business records that the consumer will see, because compaction, transactions, and offset gaps can affect it.

High lag may indicate that producers are writing faster than consumers can process, consumers are paused, listeners are slow, or the group lacks sufficient consumer/partition assignments. A lag of 0 typically indicates the group is caught up with the log at the time of measurement; new records can still arrive immediately afterward.

Check with the Kafka CLI:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-worker
```

The output typically displays `CURRENT-OFFSET`, `LOG-END-OFFSET`, and `LAG` for each partition. Read per partition to identify which partition is lagging; total group lag can hide a hot partition or a failing consumer.

## 13. Common Misconceptions

| Misconception | Correct Understanding |
|---|---|
| An offset is a unique record ID across all of Kafka | An offset is unique only within one partition; you need topic + partition + offset |
| Offset 100 is always older than offset 50 | Offset ordering can only be compared within the same partition |
| Offset equals the number of processed records | An offset is a log position; there can be gaps due to compaction, transactions, or retention |
| Commit offset 42 after processing record 42 | You usually must commit 43, which is the next position to read |
| Position equals committed offset | Position is the current read position; committed offset is the progress saved for the group |
| `earliest` always starts from offset 0 | Starts from the log start offset currently retained |
| `seek()` automatically saves the offset for the next restart | `seek()` changes the local position; you must commit if you want to save the new progress for the group |
| A lag of 30 always means exactly 30 business records remain | Lag is an offset difference; compacted/transactional data can make the visible record count differ |

## 14. Practical Workflow for Using Offsets

1. When the producer sends a record, record the topic, partition, and offset metadata if tracing is needed.
2. When the consumer receives a record, log topic/partition/offset along with the event ID to aid investigation.
3. Process business logic and durably persist results before acknowledging offsets according to the chosen policy.
4. Commit the next position to read, not the offset of the record just processed.
5. Upon restart or rebalance, the consumer resumes from the group's committed offset.
6. When replaying, determine the partition and starting offset/timestamp; evaluate the impact of reprocessing and idempotency.
7. Monitor log start, log end, committed offset, and lag per partition.
8. If an offset has been deleted by retention, choose an intentional reset policy and understand which data will be skipped or re-read.

## Checklist

- Identify a record by topic, partition, and offset.
- Understand that ordering is guaranteed only within a single partition.
- Do not assume offsets are contiguous or equal to the number of processed records.
- Distinguish log start offset, log end offset, high watermark, and last stable offset.
- Distinguish consumer position from committed offset.
- Commit the next offset after successfully processed records.
- Use `seek()` on the right partition and understand that seek does not auto-commit.
- Consider retention, compaction, and `read_committed` when offsets have gaps or are no longer valid.
- Monitor lag per partition and process records idempotently when redelivery is possible.

Offsets are the foundation for Kafka to track read positions and help applications recover from failures. When you understand per-partition offsets, distinguish position from committed offset, and commit the correct next position, a Spring Kafka application can manage consumption progress, replay, and event processing in a controlled manner.

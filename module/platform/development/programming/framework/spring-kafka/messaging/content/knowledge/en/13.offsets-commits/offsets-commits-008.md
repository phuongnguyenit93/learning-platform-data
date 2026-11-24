# Seeking to a Specific Offset

In Kafka, consumers normally resume reading from the committed offset saved for the consumer group. However, certain scenarios require moving the read position to another offset: replaying a segment of data to investigate a bug, reprocessing events after fixing logic, skipping log segments that no longer need processing, or starting from a point in time. Kafka provides the `seek()` API to change a consumer's read position on a partition.

The key point is that `seek()` changes the in-memory position of the running consumer. It does not automatically alter the committed offset saved for the group. If the consumer restarts or rebalances, the position may be restored from the old committed offset. To change the resume point durably, you must commit the new position or reset the consumer group's offsets with administrative tools while the group is stopped.

## 1. What Is Seek?

`seek()` sets a consumer's position to a specified offset on a `TopicPartition`. The next `poll()` will resume reading from that position according to the partition's available data.

For example, topic `orders` has partition 0 and the consumer is at position 500. Calling `seek()` to offset 200 causes the consumer to re-read data starting from position 200:

```text
Partition orders-0:

... 197  198  199  200  201  202  ...  499  500  501 ...
                    ^                       ^
                    |                       |
               seek to 200             old position

After seek: poll() continues from offset 200
```

An offset is a position within a single partition, so both topic and partition must be specified. Offset 200 in `orders-0` is unrelated to offset 200 in `orders-1`.

Seek is useful in scenarios such as:

- Replaying a partition from a specific offset to inspect or reprocess events.
- Resuming from a checkpoint stored separately by the application.
- Skipping a range of data verified not to require processing.
- Re-reading data after fixing processing logic.
- Moving to an offset near a timestamp under investigation.

Seek must be used deliberately because re-reading records can repeat business side effects. Consumers should be idempotent or have replay controls.

## 2. Preconditions Before Calling seek()

A consumer can only seek on partitions it currently owns (has been assigned). When using `subscribe()`, assignment is decided by the Kafka group coordinator after polling and rebalancing. Therefore, do not call `seek()` immediately after `subscribe()` before partitions are assigned.

Example of the correct order:

```java
consumer.subscribe(List.of("orders"));

// Poll to join the group and receive partition assignment.
consumer.poll(Duration.ofMillis(1000));

TopicPartition partition = new TopicPartition("orders", 0);
if (consumer.assignment().contains(partition)) {
    consumer.seek(partition, 200L);
}
```

If the application uses `assign()` to assign partitions manually, it can seek right after calling `assign()`:

```java
TopicPartition partition = new TopicPartition("orders", 0);
consumer.assign(List.of(partition));
consumer.seek(partition, 200L);
```

`assign()` does not participate in the consumer group's automatic partition distribution like `subscribe()`. When using `assign()`, the application must manage partition allocation itself and avoid multiple consumers unintentionally processing the same partition.

`KafkaConsumer` is not thread-safe. `seek()`, `poll()`, `commitSync()`, and most consumer APIs must be called on the thread owning the consumer. Never grab the consumer from a listener thread and call seek directly from a different business thread.

## 3. Seeking to an Absolute Offset with KafkaConsumer

The following example positions the consumer at offset 200 of partition `orders-0`:

```java
TopicPartition partition = new TopicPartition("orders", 0);

consumer.subscribe(List.of("orders"));
consumer.poll(Duration.ofMillis(1000));

if (!consumer.assignment().contains(partition)) {
    throw new IllegalStateException("Partition not yet assigned: " + partition);
}

consumer.seek(partition, 200L);

ConsumerRecords<String, String> records =
        consumer.poll(Duration.ofMillis(1000));
```

After `seek()`, `position(partition)` reflects the new read position. However, offset 200 might no longer correspond to a readable record if the log start offset increased due to retention, or it might fall within an offset gap caused by compaction/transactions. Kafka looks for readable data at or after the requested position according to the current log; never assume every offset number maps to an existing record.

If seeking to an offset lower than the log start offset or beyond the log end offset, the consumer may encounter `OffsetOutOfRangeException` on the next fetch. Handling depends on the `auto.offset.reset` setting or the application's error-handling logic. Check offset bounds before seeking rather than assuming the consumer will wait until the log grows to the target offset.

## 4. Seeking to the Beginning or End of a Partition

KafkaConsumer provides two convenience APIs:

```java
Set<TopicPartition> partitions = consumer.assignment();

// Move position to the log start offset of assigned partitions.
consumer.seekToBeginning(partitions);

// Move position to the current log end offset of assigned partitions.
consumer.seekToEnd(partitions);
```

`seekToBeginning()` moves the position to the start of the currently retained log, which is not necessarily offset 0. Data already removed by retention or compaction cannot be re-read.

`seekToEnd()` moves the position to the end of the log at the time of the call. The consumer will wait for new records written after that position. This is how to start following new data on assigned partitions without re-reading existing history.

To apply to a specific partition, pass a collection containing only that partition. These two methods also change only the local position and do not automatically update the group's committed offset.

## 5. Validating Offsets Before Seeking

Before seeking, check the log start and log end offsets to know the currently available data range:

```java
TopicPartition partition = new TopicPartition("orders", 0);

Map<TopicPartition, Long> beginning =
        consumer.beginningOffsets(Set.of(partition));
Map<TopicPartition, Long> end =
        consumer.endOffsets(Set.of(partition));

long startOffset = beginning.get(partition);
long endOffset = end.get(partition);
long targetOffset = 200L;

if (targetOffset < startOffset || targetOffset > endOffset) {
    throw new IllegalArgumentException(
            "Offset out of log range: start=" + startOffset
                    + ", end=" + endOffset
                    + ", target=" + targetOffset);
}

consumer.seek(partition, targetOffset);
```

This is a basic range check. `endOffsets()` returns the end of the log visible to the client according to its isolation level and cluster state; under `read_committed`, the boundary can differ from `read_uncommitted`. Data can change between the check and the seek as producers keep writing or retention runs in the background. Therefore, `OffsetOutOfRangeException` still needs to be handled in the consumer lifecycle.

A target offset equal to the log end offset is the next position, not the offset of the last record. Seeking to end means waiting for new data. A target offset equal to the log start offset is the earliest still-readable position at query time.

## 6. Relative Seek and Timestamp-Based Replay

In some situations, the application does not know the exact offset upfront and only wants to move backward or forward relative to the current position. The Kafka client can use `position()` to obtain the next position and compute the target offset:

```java
long currentPosition = consumer.position(partition);
long targetOffset = Math.max(startOffset, currentPosition - 100L);

consumer.seek(partition, targetOffset);
```

For example, stepping back 100 offsets, clamped at the log start offset. This calculation operates on offset positions and does not guarantee replaying exactly 100 business records because offset gaps may exist. If the requirement is to replay 100 actual records, you must read and count records rather than subtracting offset numbers.

When starting from a point in time, use `offsetsForTimes()` to locate the first offset whose timestamp is greater than or equal to the target timestamp:

```java
long targetTimestamp = Instant.parse("2026-01-15T10:00:00Z")
        .toEpochMilli();

Map<TopicPartition, Long> timestamps =
        Map.of(partition, targetTimestamp);
Map<TopicPartition, OffsetAndTimestamp> matches =
        consumer.offsetsForTimes(timestamps);

OffsetAndTimestamp match = matches.get(partition);
if (match != null) {
    consumer.seek(partition, match.offset());
} else {
    log.warn("No record found at or after target timestamp");
}
```

The timestamp can be `CreateTime` sent by the producer or `LogAppendTime` assigned by the broker. Determine whether the timestamp reflects business occurrence time or when Kafka wrote the record. If no matching record exists, `offsetsForTimes()` may return `null`.

## 7. Seek Only Changes Position, Not Committed Offsets

This is the most important distinction when using seek.

Suppose group `orders-worker` has committed offset 500. A running consumer calls `seek()` back to offset 200:

```text
Group committed offset:        500
Consumer position before seek: 500

consumer.seek(partition, 200L)

Consumer position after seek:  200
Group committed offset:        500 (unchanged)
```

If the consumer keeps running, it reads from position 200. However, if the consumer restarts or the partition is revoked and reassigned, the container/client may restore the position from the committed offset 500. Therefore, an in-memory seek is not a durable reset of the group's progress.

If using raw KafkaConsumer and wanting to persist the new position for the group, you can commit the target offset after seeking:

```java
long targetOffset = 200L;
consumer.seek(partition, targetOffset);

consumer.commitSync(Map.of(
        partition,
        new OffsetAndMetadata(targetOffset)));
```

The snippet above saves the next position to read as 200. On restart, the group can resume from this committed position, provided the offset remains valid and the partition is assigned to the consumer.

When replaying, never commit the target offset arbitrarily if business logic requires keeping the old checkpoint. Determine whether the replay runs on a dedicated group or intentionally alters the production group's progress. Usually, a separate group ID should be used for replay tasks so the progress of consumers serving primary traffic is not modified.

## 8. Resetting Committed Offsets with the Kafka CLI

To change the saved committed offset of a consumer group, Kafka provides the `kafka-consumer-groups.sh --reset-offsets` command. Unlike `seek()`, this is an administrative operation on the group's offsets and affects subsequent consumer runs.

First, stop all consumers participating in the group to be reset. Kafka requires the group to be in an inactive state (no active members) for offset reset operations. Then run `--dry-run` to preview the plan:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group orders-worker \
  --topic orders \
  --reset-offsets \
  --to-offset 200 \
  --dry-run
```

If the result matches the expected partitions and offsets, execute with `--execute`:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group orders-worker \
  --topic orders \
  --reset-offsets \
  --to-offset 200 \
  --execute
```

The example above applies the target offset to the partitions of the selected topic within the scope displayed by the tool. For multi-partition topics with different log start/end offsets, inspect the dry-run output and ensure the offset is valid for each partition before executing. Specific partition filtering syntax can vary by Kafka version; check `--help` on your installed script before running in production.

Common reset options:

| Option | Meaning |
|---|---|
| `--to-offset N` | Sets committed offset to position N |
| `--to-earliest` | Sets to the earliest currently retained log start offset |
| `--to-latest` | Sets to the current log end offset |
| `--shift-by N` | Shifts committed offset relatively by N offsets |
| `--to-datetime ...` | Finds position by timestamp |
| `--by-duration ...` | Shifts backward by a duration |
| `--dry-run` | Displays the plan without writing changes |
| `--execute` | Applies the offset changes |

Resetting offsets can cause consumers to re-read data or skip part of the data. Always record the initial state, verify group ID/topic/partition, and carefully read the dry-run output before executing. After resetting, restart consumers and verify the committed offsets and actual reading behavior.

## 9. Seeking in Spring Kafka with ConsumerSeekAware

When using `@KafkaListener`, Spring Kafka manages the KafkaConsumer inside the listener container. Never create another consumer or call consumer APIs directly from a business thread just to seek. Spring Kafka provides `ConsumerSeekAware` and `ConsumerSeekCallback` to ask the container to change positions on the appropriate consumer thread.

Example of seeking to configured offsets when partitions are assigned:

```java
@Component
public class OrderReplayListener implements ConsumerSeekAware {

    private final Map<TopicPartition, Long> replayOffsets = Map.of(
            new TopicPartition("orders", 0), 200L);

    @Override
    public void onPartitionsAssigned(
            Map<TopicPartition, Long> assignments,
            ConsumerSeekCallback callback) {

        assignments.keySet().forEach(partition -> {
            Long target = replayOffsets.get(partition);
            if (target != null) {
                callback.seek(
                        partition.topic(),
                        partition.partition(),
                        target);
            }
        });
    }
}
```

`onPartitionsAssigned()` is invoked when the container receives partition assignments. The callback enables requesting seeks on the proper consumer thread. The example assumes `replayOffsets` is provided from configuration or an application checkpoint; validate that offsets lie within the log range before using them.

When a listener runs with concurrency, Spring Kafka associates a callback with each consumer thread. If storing callbacks for later use, store them per thread/consumer and remove or update them when partitions are revoked; never store a single shared callback variable across all consumers. `ConsumerSeekAware` also includes callbacks such as `registerSeekCallback`, `onPartitionsRevoked`, and `onIdleContainer` to manage seek lifecycles as needed. Verify exact APIs against your Spring Kafka version.

Example listener receiving records:

```java
@KafkaListener(
        id = "ordersReplayListener",
        topics = "orders",
        groupId = "orders-replay-worker")
public void onOrder(ConsumerRecord<String, OrderCreated> record) {
    log.info("Replay record partition={}, offset={}",
            record.partition(), record.offset());
    orderService.reprocess(record.value());
}
```

Use a dedicated group ID like `orders-replay-worker` for replay flows if you do not want to alter the committed offsets of the main processing group. If intentionally replaying with the production group, coordinate seeks with commits/acknowledgments to establish the resume point after replay completes.

## 10. Seek and Rebalances

When a consumer group rebalances, partitions can be revoked and reassigned. Positions set by an earlier seek can be replaced when the container restores from committed offsets or when assignment callbacks run different logic. If seeking must occur after every assignment, place that logic in `ConsumerSeekAware.onPartitionsAssigned()` or the corresponding rebalance callback.

For example, a consumer seeks to offset 200, and then the partition is revoked. When the partition is reassigned, the container may initialize the position from the group's committed offset. If the application wants to resume from its own checkpoint, apply that checkpoint in the assignment callback whenever appropriate.

Do not seek past unfinished records in the same partition if offset commits might advance past them. When processing concurrently, track contiguously completed offsets to avoid committing past in-flight records.

## 11. Common Errors When Seeking

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `IllegalStateException` on seek | Partition has not been assigned to the consumer yet | Poll to receive assignment or call `assign()` before seeking |
| `OffsetOutOfRangeException` | Offset is lower than log start or outside valid range | Check `beginningOffsets()`/`endOffsets()` and retention; pick a valid offset or explicit reset policy |
| Seek succeeded, yet restart reads old position | Only position changed; committed offset remained unchanged | Commit the new position or reset group offsets via CLI |
| Consumer receives no records after seek | Seeked to log end, offset exceeds available data, or `read_committed` is blocked by an open transaction | Inspect LEO/LSO, isolation level, and producer activity |
| Replay causes duplicate side effects | Records reprocessed from an older offset | Use a separate replay group, idempotency keys, or deduplication |
| Seek has no effect after rebalance | New assignment restores position from committed offset or another callback overwrites it | Place seek inside `onPartitionsAssigned()` and check callback order |
| CLI reset reports group is active | Consumers are still participating in the group | Stop all consumers in the group and re-run dry-run |

## 12. Safe Replay Workflow

A controlled replay process can follow these steps:

1. Identify the topic, partitions, and offset range to re-read.
2. Check log start/end offsets, retention, and isolation level to confirm data is still available.
3. Decide whether to use a separate consumer group for replay or alter the existing group's committed offsets.
4. Evaluate side effects and ensure handlers are idempotent or have duplicate prevention.
5. If using `seek()`, ensure partitions are assigned and execute on the consumer thread.
6. If resetting group offsets, stop consumers, run `--dry-run`, inspect results, and only then run `--execute`.
7. Start consumers, verify actual partitions/offsets, and monitor lag, processing errors, and replayed record counts.
8. After completion, verify the group resumes from the desired checkpoint without missing new data.

## 13. Common Misconceptions

| Misconception | Correct Understanding |
|---|---|
| `seek()` changes committed offsets | `seek()` only changes the local position; commit or reset group offsets to persist |
| You can seek immediately after `subscribe()` | You must wait for partition assignment, typically by polling first |
| `seekToBeginning()` always goes to offset 0 | It goes to the currently retained log start offset |
| `seekToEnd()` reads the last record | It sets position to the current end of log to wait for new records |
| Subtracting 100 offsets means replaying 100 records | Offsets can have gaps; offset difference does not always equal record count |
| CLI offset reset works while consumers are running | The group must be inactive; stop consumers before resetting |
| Seeking to any offset always returns a record with that exact offset | That offset may no longer exist or be a gap; the consumer reads from the current log at or after the requested position |
| Replaying with the production group does not affect main progress | Replaying can alter positions/committed offsets and cause duplicate reads or skipped data |

## Checklist

- Identified the exact topic, partitions, and target offsets.
- Consumer has been assigned partitions before calling `seek()`.
- Checked log start/end offsets and whether target offsets were removed by retention.
- Understood that `seek()` only changes position and does not auto-update committed offsets.
- Explicitly decided whether to commit the new position, use a dedicated replay group, or reset group offsets.
- If using the Kafka CLI, verified the group is inactive and checked `--dry-run` before `--execute`.
- With Spring Kafka, used `ConsumerSeekAware`/`ConsumerSeekCallback` instead of accessing the consumer from another thread.
- Implemented idempotency or deduplication to control side effects during replay.
- Monitored actual offsets, lag, and processing outcomes after seeking.

`seek()` is a powerful tool for controlling per-partition read positions. By clearly distinguishing position from committed offsets, waiting for assignment before seeking, and verifying log bounds, applications can replay or shift read positions in a controlled manner. In Spring Kafka, `ConsumerSeekAware` integrates seek operations into the listener container lifecycle; for durable changes to group progress, use commits or controlled offset reset procedures.

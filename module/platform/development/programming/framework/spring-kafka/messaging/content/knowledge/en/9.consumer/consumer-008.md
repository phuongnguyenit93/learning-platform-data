# Distinguishing Position, Committed Offset, and End Offset

## 1. Why distinguish these three offset milestones?

When a Kafka consumer reads a partition, three milestones are commonly used to describe progress:

- **Position**: the current read position of the consumer instance; indicates the next offset the consumer will fetch on poll.
- **Committed offset**: the read position saved for the consumer group; the consumer can resume from here after a restart or rebalance.
- **End offset**: the upper boundary of readable data in the partition under the active isolation level.

These three values serve three distinct purposes. Position reflects the in-memory read progress of the current consumer; committed offset reflects the durably saved progress for the group; end offset reflects the boundary of currently available readable data. Confusing them easily leads to wrong conclusions about consumer lag, duplicate processing, or lost records.

In Spring Kafka, `@KafkaListener` is invoked by the listener container after the Kafka consumer polls records. The container manages position and commits according to `AckMode`; the application typically observes each record's offset via headers or metadata. Understanding these underlying Kafka Consumer concepts helps accurately read listener state in operations.

## 2. What is Position?

`position` is the next offset that a Kafka consumer will read from a `TopicPartition`. When a consumer polls and receives records with offsets `100`, `101`, and `102`, the position typically advances to `103` after those records are returned from `poll()`.

Position belongs to the runtime state of a single consumer instance. It can change when:

- The consumer calls `poll()` and receives additional records.
- The application calls `seek()` to move the read position.
- The consumer is assigned partitions after joining a group and restores the starting position.
- The consumer is reassigned partitions after a rebalance.

Position does not automatically mean that preceding records have been processed successfully in business logic. `poll()` can return multiple records and advance the position before the application finishes processing every record in the batch. If the application commits the position while unprocessed records remain, those records may be skipped after a restart.

Example:

```text
Partition orders-0

Offset:       100   101   102   103   104   105
              [A]   [B]   [C]   [D]   [E]   [F]
                       poll() returns A, B, C
                                      |
                                      v
                               position = 103
```

Position `103` means the next read starts from offset `103`. It does not mean offsets `100` through `102` have been committed for the group. Business processing and committing are two separate steps.

### Is Position the offset of the last read record?

No. Position is the next offset, not the offset of the last record. If the last returned record had offset `102`, position is typically `103`. However, offsets can have gaps due to log compaction, transaction markers, or records withheld from the consumer by isolation level; thus the next offset does not always equal the last observed record's offset plus one or match the observed record count.

## 3. What is Committed Offset?

Committed offset is the next position a consumer group has saved for each partition. Kafka stores this information in the group's offset management mechanism, independent of the consumer instance's memory.

Example where a consumer successfully processes record offset `102`, then commits offset `103`:

```text
Last processed record:     102
Committed offset:          103
When resuming reading:     starts from offset 103
```

Committed offsets are managed per consumer group and partition pair. Two different groups can read the same topic while having different committed offsets. When one consumer instance stops and another takes over the partition, the new consumer restores progress from the group's committed offset.

If the group has no committed offset for the partition yet, Kafka applies `auto.offset.reset` to pick the starting position. If the committed offset is no longer valid, such as falling before the beginning offset because retention deleted older data, the reset policy may also apply depending on configuration. `auto.offset.reset` does not overwrite a still-valid committed offset.

### Committing an offset is not processing a record

Kafka does not automatically know whether a listener's database update or business operation succeeded. The application or listener container decides when to commit. If a commit happens before processing finishes, the application risks losing processing work. If processing finishes but the process stops before committing, the record may be redelivered and cause duplicate side effects.

Therefore, business consumers are typically designed for at-least-once semantics: process successfully then commit, while ensuring handlers are idempotent to tolerate redelivery.

## 4. What is End Offset?

End offset is the upper boundary of data in a partition, represented by the next offset after the range of data readable by the consumer. If the end offset is `106`, the offset range prior to that boundary may contain records with offsets less than `106`, depending on retention, compaction, and isolation level.

End offset is not the offset of the last record. If the last record has offset `105`, the end offset is typically `106`. It serves as a boundary to identify data ahead of the consumer and calculate lag.

You can retrieve the end offset using the Kafka Consumer API:

```java
Map<TopicPartition, Long> endOffsets =
        consumer.endOffsets(Set.of(topicPartition));

Long endOffset = endOffsets.get(topicPartition);
```

This call queries the partition's end offset; it is not a record-reading operation and does not alter the consumer's position.

### Beginning offset and retention

A partition also has a beginning offset, which is the smallest offset still retained that a consumer can read. As retention deletes older segments or log compaction removes older records, the beginning offset can advance. Therefore, do not assume a partition always starts at offset `0` or that all historical offsets still exist.

The readable range can be visualized as:

```text
Beginning offset                         End offset
       |                                      |
       v                                      v
       40  41  42  43  44  45  46  47  48  49
       |<--------- readable data ----------->|
```

If a group's committed offset is smaller than the beginning offset, the consumer cannot re-read data that has already been deleted. Kafka handles out-of-range offsets according to `auto.offset.reset` such as `earliest`, `latest`, or `none`.

## 5. Distinguishing LEO, High Watermark, and Last Stable Offset

When discussing end offset, note that Kafka has several boundaries related to replication and transactions:

| Milestone | Meaning |
|---|---|
| Log End Offset (LEO) | The next offset the partition leader will assign to a new record; reflects the tail of the log on the leader |
| High watermark (HW) | Boundary of data sufficiently replicated under the replication protocol; regular consumers do not read past HW |
| Last Stable Offset (LSO) | Stable read boundary for `read_committed` consumers; open transactions can keep LSO lower than HW |

LEO can be higher than HW when the leader has written records that followers have not yet replicated. For a `read_uncommitted` consumer (`isolation.level=read_uncommitted`), the available read range is bounded by the high watermark. For `isolation.level=read_committed`, the consumer reads only records from committed transactions and does not read past the last stable offset.

Consequently, the end offset returned by the consumer API depends on the isolation level: with `read_uncommitted`, this boundary is based on HW; with `read_committed`, it is based on LSO. When an open transaction exists, LSO can be lower than HW. This is why a `read_committed` consumer may not yet see records already written by the leader.

```text
LEO       = 120   leader has assigned the next offset as 120
HW        = 118   read_uncommitted consumer reads up to boundary 118
LSO       = 115   read_committed consumer reads up to boundary 115

Offsets 115..117 may be blocked by an open transaction.
```

The values above only illustrate the boundaries. End offset is not the count of processed records and should not be equated with LEO in all contexts.

## 6. Comparing Position, Committed Offset, and End Offset

| Criterion | Position | Committed offset | End offset |
|---|---|---|---|
| Scope | One consumer instance and an assigned partition | One consumer group and partition | One partition, per querying consumer's isolation level |
| Storage | Consumer's runtime state | Durably stored by Kafka for the group | Derived from log/replication/transaction state |
| Meaning | Next offset the consumer will read | Next offset saved by the group for recovery | Upper boundary of data the consumer can read |
| Changed by | `poll()`, `seek()`, assignment | Group offset commits | New records, replication, transaction completion, retention/truncation |
| Proves business logic processed? | No | Only reflects that the app committed per its policy | No |
| Used for | Tracking current read progress | Recovering after restart/rebalance and calculating group lag | Determining data ahead and calculating lag |

Example of a partition with:

```text
committed offset = 41
position         = 45
end offset       = 52
```

This can be interpreted as:

- The group has saved progress so the next read starts from offset `41`.
- The current consumer has polled up to the next position `45`.
- The consumer is `7` offset units away from the observed end offset.
- The span from committed offset to position is `4` uncommitted offset units; records in this range may be in-flight or already processed but not yet committed.

Do not interpret these subtractions as exact record counts in every case. Log compaction, transaction markers, and offset gaps can make offset distance differ from the actual number of records.

## 7. How is consumer lag calculated?

Consumer lag describes the distance between a consumer group's read progress and the data available at the end of a partition. The standard group-level calculation is:

\[
\text{Committed lag} = \text{End offset} - \text{Committed offset}
\]

To view the current consumer instance's progress, you can use:

\[
\text{Position lag} = \text{End offset} - \text{Position}
\]

The two values answer two different questions:

- Committed lag: how far is the group from the end offset based on durably saved progress?
- Position lag: how far is the current consumer instance from the end offset based on its in-memory read position?

Example with `committed=41`, `position=45`, `end=52`:

| Metric | Calculation | Result |
|---|---:|---:|
| Committed lag | 52 - 41 | 11 |
| Position lag | 52 - 45 | 7 |
| Uncommitted position relative to committed | 45 - 41 | 4 |

Committed lag being larger than position lag can be normal when the consumer has polled records but has not yet committed. If the listener processes asynchronously, this gap may include records awaiting completion. Committing too frequently increases commit overhead; committing too infrequently can keep committed lag large even though the listener has already processed most records.

Lag is typically expressed in offset distance, not necessarily exact message count. In compacted topics or transactional streams, offsets may have gaps or records may be hidden by the isolation level.

## 8. Observing all three milestones via the Kafka Consumer API

The Kafka Java Consumer provides APIs to inspect position, committed offset, and end offset. The example below uses `assign()` to inspect a specific partition directly:

```java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-monitor");
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

TopicPartition partition = new TopicPartition("orders", 0);

try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props)) {
    // assign() assigns the partition directly; subscribe() is not used in this example.
    consumer.assign(List.of(partition));

    long position = consumer.position(partition);

    Map<TopicPartition, OffsetAndMetadata> committedOffsets =
            consumer.committed(Set.of(partition));
    OffsetAndMetadata committed = committedOffsets.get(partition);

    Map<TopicPartition, Long> endOffsets =
            consumer.endOffsets(Set.of(partition));
    long endOffset = endOffsets.get(partition);

    System.out.println("Position: " + position);
    System.out.println("Committed: "
            + (committed == null ? "none" : committed.offset()));
    System.out.println("End offset: " + endOffset);
}
```

`assign()` manually assigns the partition to the consumer; this example does not participate in group automatic partition distribution via `subscribe()`. The consumer can still query committed offsets by `group.id`, though the example only observes and does not commit. In a real application, do not let a monitoring consumer arbitrarily commit or seek on the same group while business consumers are active.

If using `subscribe()`, the consumer must call `poll()` to join the group and receive assignments before querying `position()` for a partition. Do not call `position()` on a partition not yet assigned to the consumer.

### Seek changes position

`seek()` moves the consumer's position to a specific offset:

```java
consumer.seek(partition, 100L);
long position = consumer.position(partition); // 100
```

This operation changes the read position in the current consumer. It does not write a committed offset for the group. If the consumer stops before committing the new position, the next startup may resume from the old committed offset. If you want to persist the sought position, commit the offset according to the appropriate rules.

## 9. Observing record offsets in Spring Kafka

With `@KafkaListener`, applications often need to know which topic and partition the current record came from and what its offset is. Spring Kafka maps this information into message headers:

```java
@Component
public class OrderListener {

    @KafkaListener(topics = "orders", groupId = "order-service")
    public void onOrder(
            OrderCreated event,
            @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
            @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
            @Header(KafkaHeaders.OFFSET) long offset) {

        log.info("Received orderId={}, topic={}, partition={}, offset={}",
                event.orderId(), topic, partition, offset);
    }
}
```

These headers report the offset of the specific record received by the listener. They are neither the consumer's current position nor the group's committed offset.

If you need to control commits, configure the listener container via `AckMode` and use `Acknowledgment` when choosing a manual mode. Do not use the offset header of the last record in a batch to commit arbitrarily if earlier records are not yet finished or parallel processing has not completed.

## 10. Observing group offsets with the Kafka CLI

The `kafka-consumer-groups.sh --describe` command shows a consumer group's read progress per partition:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-service
```

Common columns:

| Column | Meaning |
|---|---|
| `CURRENT-OFFSET` | Committed offset currently stored for the group/partition |
| `LOG-END-OFFSET` | End offset used by the tool to compare progress against the end of the log |
| `LAG` | Distance between log end offset and committed offset as computed by the tool |
| `CONSUMER-ID` / `HOST` | Consumer instance currently assigned the partition, if any |

Illustrative example:

```text
GROUP         TOPIC   PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
order-service orders  0          41               52              11
order-service orders  1          80               80              0
order-service orders  2          25               40              15
```

Partition 1 has zero offset lag at the moment of observation. Partitions 0 and 2 still have gaps of 11 and 15 respectively. This is a point-in-time snapshot; lag can grow when producers write faster than consumers or shrink as consumers catch up.

The CLI displays the group's committed offset, not the consumer's latest runtime position. Thus, `LAG` can be larger than the number of records genuinely not yet polled by the listener if records have been polled/in-flight but not yet committed.

## 11. Impact of AckMode and auto-commit

In Spring Kafka, the listener container typically manages offset commits. Since Spring Kafka 2.3, the framework automatically sets `enable.auto.commit=false` if the application has not explicitly configured it, letting the container control commits per `AckMode`.

| AckMode | Impact on committed offset |
|---|---|
| `RECORD` | Commits after the listener successfully processes each record |
| `BATCH` | Commits after all records in the polled batch have been processed successfully |
| `TIME`, `COUNT`, `COUNT_TIME` | Commits processed offsets when the corresponding time/count threshold is reached |
| `MANUAL` | Listener calls `acknowledge()`; container handles commit via the manual/batch mechanism |
| `MANUAL_IMMEDIATE` | Commits immediately when acknowledge is called on the consumer thread |

Position can advance after a poll while the committed offset remains unchanged. This is normal behavior with `BATCH` or `MANUAL`. If the listener processes asynchronously, ensure only contiguous completed offsets per partition are committed. Never commit past an unprocessed record merely because position has advanced.

Example: a poll returns offsets `10`, `11`, `12`; the application finishes `10` and `12` while `11` is still running. You cannot safely commit `13` because upon restart, record `11` would be skipped. The committed offset must reflect the contiguous boundary of successfully processed records—in this case, at most `11` (the next position after offset `10`).

## 12. Situations prone to misunderstanding

### Position is greater than committed offset

This is a common situation. The consumer has polled records, but the commit point under `AckMode` has not been reached yet, or the application is still processing a batch. If the instance stops before committing, those records may be redelivered.

### Committed offset equals end offset

The group has committed up to the current upper boundary. If producers write more records, end offset increases and lag can appear. Being equal at one moment does not mean the topic will not receive new records.

### Committed offset is less than beginning offset

Older data the group wants to read may have been deleted by retention. The consumer encounters an offset-out-of-range condition and subsequent behavior depends on `auto.offset.reset`. `earliest` only means reading from the oldest remaining beginning offset, not recovering deleted data.

### End offset is greater than position, yet the listener sees no records

Check whether the consumer is assigned the right partition, whether it is paused, what `isolation.level` is set, whether there is an open transaction, whether records were filtered/compacted, and whether deserializers failed. End offset is only a boundary; it does not guarantee every offset below it holds a record delivered to the listener.

### Lag grows even though the listener is still processing

Producers may be writing faster than processing speed, batches may be waiting to commit, the consumer may be rebalancing, or a hot partition may skew group progress. Inspect per-partition lag, position, committed offset, throughput, and processing time rather than looking only at a single aggregate number.

## 13. Testing position, committed offset, and end offset

Integration tests should verify the relationship among the three milestones across concrete operations:

1. Create a topic with one partition and send a known set of records.
2. Assign a new consumer group, configure `auto.offset.reset=earliest`, and verify the starting position is at the existing beginning offset.
3. Poll one batch, check that position advances while committed offset remains unchanged before commit.
4. Finish processing the batch and commit, then verify committed offset equals the next position to read.
5. Stop the consumer and start another instance in the same group; verify the new consumer resumes from the committed offset.
6. Use `seek()` to change position and verify committed offset does not change until committed.
7. Send additional records and check that end offset increases; verify lag recalculates.
8. If using transactions, test the difference between `read_uncommitted` and `read_committed` when a transaction is open or aborted.

With Spring Kafka, you can use `spring-kafka-test` or the Kafka test starter matching your Spring Boot line. To test rebalances, retention, and transaction isolation realistically, add tests with a broker/container matching your target Kafka version.

## 14. Summary

- Position is the next offset the current consumer instance will read; it changes with polls, seeks, and assignments.
- Committed offset is the next offset durably stored for a consumer group and partition; it is used to recover after restarts/rebalances.
- End offset is the upper boundary of data a consumer can read; it is not the offset of the last record.
- LEO, high watermark, and last stable offset are distinct boundaries; isolation level affects the end offset a consumer sees.
- Committed lag and position lag reflect two different kinds of progress; offset distance does not always equal the exact record count.
- Spring Kafka listener containers manage commits according to `AckMode`; position can advance ahead of committed offset.
- `@KafkaListener` can receive a record's topic, partition, and offset via `KafkaHeaders`, but those headers are not the committed offset.

When you can read all three milestones—position, committed offset, and end offset—your team can distinguish how far the consumer has polled, how much progress the group has persisted, and how much data lies ahead. This forms the foundation for diagnosing consumer lag, controlling commits, and operating reliable Spring Kafka messaging flows.

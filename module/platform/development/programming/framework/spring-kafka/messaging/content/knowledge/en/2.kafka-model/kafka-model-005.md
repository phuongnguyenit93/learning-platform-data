# Offsets and reading positions

In Kafka, a consumer does not read a topic as a single list. Each topic is split into partitions; each partition is its own ordered log, and each record in the log has an **offset**. Consumers use offsets to determine where to read next, while a consumer group stores the **committed offset** to know where to resume after a consumer restarts or a partition is reassigned to another consumer.

Understanding these markers helps control event replay, prevent missed data, and explain why a record can be processed more than once.

## 1. An offset is a position within a partition

Kafka assigns an offset to each record when it is written to a partition. Offsets start at 0 in a new log and increase in the write order of that partition. For example, topic `orders` has two partitions:

| Partition | Sample offsets | Meaning |
|---|---:|---|
| `orders-0` | 0, 1, 2, 3, ... | Record order in partition 0 |
| `orders-1` | 0, 1, 2, 3, ... | Record order in partition 1 |

Offsets are only meaningful together with a topic and partition. `orders-0` offset `12` and `orders-1` offset `12` are two different positions. Therefore, a single offset alone cannot uniquely identify a record across the entire cluster.

Several important implications:

- Ordering is guaranteed inside each partition. Kafka does not provide a total order across partitions of the same topic.
- An offset is a log position, not a business sequence number, event creation time, or order ID.
- Offsets are assigned when records are written to a partition. Deleting old records via retention or compaction does not renumber subsequent offsets from the beginning.
- Records observed by a consumer do not necessarily have contiguous offsets. Compaction can remove older versions; consumers using `read_committed` also skip records belonging to aborted transactions.

If an application needs a stable event identifier across retries or multiple topics, include a field such as `eventId` in the payload. Never use offsets in place of a business ID.

## 2. Distinguishing three position markers

When monitoring a partition, distinguish **log end offset**, **consumer position**, and **committed offset**. All three relate to offsets, yet answer three different questions.

| Marker | What does it represent? | When does it usually change? |
|---|---|---|
| Log end offset | Current end of the log; usually represented as the next offset to be assigned to a new record | When producers append new records |
| Consumer position | Next offset the consumer will fetch on the next read | When `poll()` returns records or when the application explicitly calls `seek()` |
| Committed offset | Resumption point durably stored for a consumer group | When the consumer/container commits offsets |

For example, suppose a partition has records from offset `100` to `103`. A `poll()` call returned records `102` and `103`, while the application has only finished processing up to offset `101`:

| Value | Example | Interpretation |
|---|---:|---|
| Log end offset | 104 | The next written record will receive offset 104 |
| Consumer position | 104 | The consumer has fetched data through the end of this poll; the next fetch starts at position 104 |
| Committed offset | 102 | If the consumer stops right now, the group will resume from offset 102 |

A common pitfall is that `poll()` can advance the consumer position ahead of business processing progress. Receiving a record does not mean the application has finished processing it successfully. If `104` is committed while records `102` and `103` remain unprocessed, the next restart will begin at `104` and may skip those two records.

## 3. Committed offset is the next starting point

Kafka stores offsets under a key consisting of **consumer group + topic + partition**. Committed data is managed internally in the `__consumer_offsets` topic. Each consumer group maintains independent progress: two groups reading `orders` can sit at different offsets without affecting each other.

The committed value indicates the **next offset to read**, not the offset of the last processed record. If an application successfully processes record offset `41`, it needs to commit `42` so the next read begins at `42`.

This rule also explains failure behavior:

1. The consumer reads record `41`.
2. The application processes the record successfully.
3. The consumer commits offset `42`.
4. The consumer stops or the partition is reassigned to another consumer.
5. The takeover consumer reads starting at offset `42`.

If the application processed `41` but stopped before committing `42`, Kafka still considers `41` unacknowledged. The next consumer can read that record again. That is why handlers must support safe reprocessing (idempotency) when a system operates under at-least-once semantics.

## 4. Offset commits and delivery semantics

When you commit determines what can happen if a process fails mid-flight:

| Order | Risk if process stops midway | Typical behavior |
|---|---|---|
| Commit first, process later | Offset has advanced while business work is incomplete | Processing for committed records may be lost |
| Process successfully first, commit later | Business work succeeded while offset is not saved | Records may be redelivered and processed redundantly |

For standard event processing, prefer completing business side effects before acknowledging the offset. This supports at-least-once delivery: unacknowledged records can be redelivered, so handlers must tolerate duplicates. You can use a unique `eventId`, database unique constraints, upsert operations, or a processed-events tracking table to guard against duplicate side effects.

Kafka transactions can coordinate writing output records and committing input offsets within a single Kafka transaction. This is the foundation for consume-transform-produce flows with exactly-once semantics within Kafka's scope. If a handler also writes to a database or calls an external system, a Kafka transaction does not automatically make that external side effect exactly-once; you still need idempotency, the outbox pattern, or appropriate coordination mechanisms.

## 5. Choosing the initial position with `auto.offset.reset`

When a consumer group has no valid committed offset for a partition yet, Kafka needs a policy to decide where to start. The `auto.offset.reset` setting determines this behavior:

| Value | Behavior |
|---|---|
| `earliest` | Start from the earliest offset currently available in the log |
| `latest` | Start from the end of the log at the moment the reading position is initialized; older records may be skipped for a new group |
| `none` | Throw an error if no valid committed offset is found |

`auto.offset.reset` **does not overwrite an existing valid committed offset** on every application startup. It is only consulted when the group has no offset yet or the stored offset is no longer valid, such as falling before the retained portion of the log. Consequently, changing `earliest` to `latest` will not automatically jump an active group to the end of a topic if that group already has a valid offset.

Example Spring Boot consumer configuration:

```yaml
spring:
  kafka:
    consumer:
      group-id: billing-v1
      auto-offset-reset: earliest
      enable-auto-commit: false
    listener:
      ack-mode: record
```

Here:

- `group-id` defines the consumer group's independent reading progress.
- `auto-offset-reset: earliest` requests reading from the earliest retained data if the group lacks a valid offset.
- `enable-auto-commit: false` lets the Spring Kafka container manage commits according to the acknowledgment mode. Since Spring Kafka 2.3, the framework defaults `enable.auto.commit` to `false` if unset by the application; declaring it explicitly in the example clarifies intent.
- `ack-mode: record` tells the container to commit after the listener finishes processing each record.

Changing `group-id` creates a separate reading progress track. This is a useful way to launch a new consumer and re-read data under the reset policy, though you must plan ahead for the business impact of replaying events.

## 6. How does Spring Kafka manage offsets?

With `@KafkaListener`, Spring Kafka typically manages consumers and commits offsets through the listener container. A listener can accept a `ConsumerRecord` to inspect record metadata:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;

@KafkaListener(topics = "orders", groupId = "billing-v1")
public void onOrderCreated(ConsumerRecord<String, OrderCreated> record) {
    process(record.value());

    log.info(
        "Processed topic={}, partition={}, offset={}",
        record.topic(), record.partition(), record.offset()
    );
}
```

`record.offset()` reports the record's position in the partition. It does not prove that the offset has been committed. Committing depends on the acknowledgment mode and the listener container's processing outcome.

Common acknowledgment modes:

| Mode | Commit timing |
|---|---|
| `RECORD` | After the listener finishes processing each record |
| `BATCH` | After all records from a single `poll()` finish processing |
| `MANUAL` | Listener explicitly acknowledges via `Acknowledgment`; the container commits according to this mode's rules |
| `MANUAL_IMMEDIATE` | Commits immediately when the listener acknowledges on the consumer thread |

`BATCH` is the default mode of the listener container. With a batch listener, the application processes a list of records in one invocation; pick a mode suited to the listener style and make sure you only acknowledge once the corresponding work is complete.

If manual acknowledgment is needed, configure the listener in `manual` mode and only call `acknowledge()` after processing succeeds:

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: manual
```

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;

@KafkaListener(topics = "orders", groupId = "billing-v1")
public void onOrderCreated(
        ConsumerRecord<String, OrderCreated> record,
        Acknowledgment acknowledgment) {

    process(record.value());
    acknowledgment.acknowledge();
}
```

If `process()` throws an exception before acknowledgment, the offset is not acknowledged by this code and the container/error handler can apply the configured retry or recovery policy. If you acknowledge before `process()`, the application risks skipping the record if processing fails afterward.

## 7. Re-reading from another position

A Kafka consumer can change its consumer position via `seek()` operations on a `TopicPartition`. Common operations include:

- `seek(partition, offset)`: sets the next reading position to the specified offset.
- `seekToBeginning(partitions)`: moves the reading position to the start of the retained log for the selected partitions.
- `seekToEnd(partitions)`: moves the reading position to the end of the log for the selected partitions.
- `offsetsForTimes(...)`: looks up the earliest offset with a timestamp greater than or equal to the requested timestamp; results may be empty if the partition has no matching record yet.

`seek()` updates the consumer's in-memory reading position. It does not automatically change the committed offset saved for the group. If the consumer stops before the new position is committed, the next startup may revert to the old committed offset.

In Spring Kafka, you can use mechanisms like `ConsumerSeekAware` or listener container APIs to perform seeks tied to the consumer lifecycle. Kafka consumers are not safe for concurrent multi-threaded access; seek operations must run through container hooks or on the consumer thread, never called arbitrarily from business threads.

Replaying data via seeking or resetting offsets can cause the application to reprocess events that already produced side effects. Ensure handlers are idempotent and clearly define the partition and offset scope before replaying.

## 8. Retention, compaction, and non-contiguous offsets

Offsets represent positions in log history, so never assume the first record a consumer reads always has offset 0 or that two consecutive records always differ by an offset of exactly 1.

- **Retention:** Kafka deletes old segments per storage policy. The earliest readable offset may be greater than 0. If the committed offset falls behind this boundary, the consumer encounters an out-of-range offset and Kafka applies `auto.offset.reset` (or throws an error with `none`).
- **Compaction:** On compacted topics, Kafka may keep only the latest version of a key and remove older versions. Gaps in offsets are normal.
- **Transactions:** Consumers using `isolation.level=read_committed` only receive records from committed transactions. Records from aborted transactions are skipped; while a transaction remains open, the stable readable boundary may temporarily lag behind the log end offset.

Therefore, do not advance offsets by assuming the next record is always `currentOffset + 1`. Let the Kafka consumer drive reading forward and use the actual offset on each `ConsumerRecord` for logging or reconciliation.

## 9. Tracking progress and consumer lag

You can inspect a group's committed offset, log end offset, and lag using Kafka CLI tools:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-v1 \
  --describe
```

The output typically includes columns like `CURRENT-OFFSET`, `LOG-END-OFFSET`, and `LAG` per partition:

| Column | Meaning |
|---|---|
| `CURRENT-OFFSET` | Current committed offset of the group |
| `LOG-END-OFFSET` | End of log marker reported by the tool for the partition |
| `LAG` | Difference between the two markers above, used to estimate remaining backlog |

Lag is an offset-based metric, not always the exact count of unprocessed application records. Compaction, transactions, and offset gaps without records can cause those two numbers to differ. When lag climbs steadily, check processing speed, listener errors, retries, partition count, active consumer count, and rebalance status.

If you need to rewind a group to the start of a topic, you can run a reset command when the group has no active consumers. Preview the result first with `--dry-run`:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-v1 \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --dry-run
```

Replace `--dry-run` with `--execute` only after verifying the exact group, topic, and partition scope. Resetting offsets alters the group's reading progress; it can trigger a massive replay and repeat business side effects.

## 10. Common issues

| Symptom | Possible cause | How to investigate |
|---|---|---|
| New group does not read old records | `auto-offset-reset` is set to `latest` | Check group id and reset policy; consider `earliest` if retained logs must be read |
| Changed `auto-offset-reset` but reading position did not change | Group already has a valid committed offset | Check `CURRENT-OFFSET`; intentionally reset offsets if replay is desired |
| A record is processed twice | Processed successfully but stopped before commit; rebalance or retry | Check commit timing and make the handler idempotent |
| Some records appear to be skipped | Commit ran ahead of processing, or group started at `latest` | Compare position, committed offset, reset policy, and listener logs |
| Non-contiguous offsets | Retention, compaction, or aborted transactions | Do not assume adjacent offsets; verify actual records and isolation level |
| Lag grows even while consumer is running | Slow processing, repeated errors, retries, or insufficient consumers/partitions | Inspect per-partition lag, processing duration, errors, and group status |

## 11. Consumer design checklist

1. Choose a stable `group-id` for a processing flow; only change groups when you genuinely want an independent progress track.
2. Choose `earliest`, `latest`, or `none` according to requirements when the group lacks a valid offset.
3. Clearly define when business work is considered complete and commit only after that point.
4. Design idempotent handlers because uncommitted records can be redelivered.
5. Do not treat `record.offset()` or consumer position as proof of commit.
6. Monitor lag per partition and check rebalances and retries when progress looks abnormal.
7. Before seeking or resetting, define the replay scope and assess side effects on databases or external services.

When reading a record, always tie its offset to its topic and partition. When recovering a consumer, look at the committed offset of the right group. These two rules form the foundation for accurately explaining which record a consumer will read next and what happens after a failure or rebalance.

# Seeking to the Beginning or End of a Partition

A Kafka consumer can change its read position within a partition instead of always resuming from the committed offset. That operation is called a **seek**. In Spring Kafka, applications typically use **ConsumerSeekAware** and **ConsumerSeekCallback** to seek to the beginning, the end, or a specific offset.

Seeking is useful when you need to replay data to rebuild state, or skip backlog to receive only new events. Before using it, distinguish **position** in a running consumer from the **committed offset** saved for the consumer group.

## 1. Beginning Offset and End Offset

Each partition is an independent log. The consumer position represents the next offset the consumer will read.

- **Beginning offset** is the lowest offset still readable in the partition at query time. It can be greater than 0 because Kafka has deleted old data per retention.
- **End offset** is the position immediately after the last currently available record. This is the next offset where a new record will be written, not the offset of the last record.

Example:

| Record | Offset |
|---|---:|
| Event A | 105 |
| Event B | 106 |
| Event C | 109 |
| End offset | 110 |

Offsets 107 and 108 may no longer have records due to compaction or data deletion. The beginning offset is 105, and the end offset is 110.

```mermaid
flowchart LR
    B[Beginning: 105] --> A[Event A: 105]
    A --> C[Event B: 106]
    C --> D[Offsets 107-108 empty]
    D --> E[Event C: 109]
    E --> F[End: 110]
    F --> N[New records start at 110]
```

Therefore, never assume the beginning offset is always 0 or that offsets in the log are always contiguous.

## 2. Seeking to the Beginning of a Partition

Seeking to the beginning moves the consumer's position to the currently available beginning offset. The consumer will re-read records still retained by Kafka in the partition.

Spring Kafka provides overloads to seek a single partition:

```java
callback.seekToBeginning("order-events", 0);
```

Or all partitions currently assigned to the consumer:

```java
callback.seekToBeginning(assignments.keySet());
```

For example, a partition has beginning offset 105 and the consumer is at position 110. After seeking to the beginning, the consumer re-reads Event A at offset 105 and continues through the remaining records.

Suitable use cases:

- Replaying retained history to rebuild a read model.
- Reloading a cache or local state from an event log.
- Re-running the processing flow after fixing logic.
- Inspecting or reprocessing data in a controlled environment.

Seeking to the beginning can cause business logic to re-run many events. Consumers need idempotency or duplicate-handling mechanisms, especially when events create side effects in databases or external services.

## 3. Seeking to the End of a Partition

Seeking to the end moves the position to the end offset Kafka determines when the seek operation is applied. The consumer skips the backlog before that position and waits for records at subsequent offsets.

```java
callback.seekToEnd("order-events", 0);
```

Or seek all assigned partitions:

```java
callback.seekToEnd(assignments.keySet());
```

For example, the current end offset is 110. After seeking, the consumer waits for records from offset 110 onward. Records with offsets lower than 110 will not be read by this consumer in the current run.

Suitable use cases:

- Monitoring consumers that only need new events produced from startup onward.
- Temporary jobs that only watch new changes.
- New streams that already loaded a snapshot and only need to continue from data produced after the snapshot.

Do not seek to the end if the consumer needs to process all unprocessed events. This operation can skip data waiting in the partition.

## 4. Using ConsumerSeekAware in Spring Kafka

**ConsumerSeekAware** allows a listener to receive callbacks to control the consumer's position. Spring Kafka registers callbacks per consumer thread; when partitions are assigned, the listener can choose to seek to the beginning or end.

Example of a listener that always seeks to the beginning whenever partitions are assigned:

```java
import java.util.Map;

import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.listener.ConsumerSeekAware;
import org.springframework.kafka.listener.ConsumerSeekAware.ConsumerSeekCallback;
import org.springframework.stereotype.Component;

@Component
public class ReplayFromBeginningListener implements ConsumerSeekAware {

    @Override
    public void registerSeekCallback(ConsumerSeekCallback callback) {
        // This example only seeks inside onPartitionsAssigned.
    }

    @Override
    public void onPartitionsAssigned(
            Map<TopicPartition, Long> assignments,
            ConsumerSeekCallback callback) {

        callback.seekToBeginning(assignments.keySet());
    }

    @KafkaListener(
        topics = "order-events",
        groupId = "replay-service"
    )
    public void listen(OrderCreated event) {
        // Process events replayed from the beginning of the partition.
    }
}
```

The **onPartitionsAssigned** method is called when the consumer receives partitions, including the initial assignment and subsequent rebalances. The **assignments** map contains the newly assigned partitions along with their current positions before the seek callback is applied.

To skip the backlog and start from the end, replace the call inside the callback with:

```java
@Override
public void onPartitionsAssigned(
        Map<TopicPartition, Long> assignments,
        ConsumerSeekCallback callback) {

    callback.seekToEnd(assignments.keySet());
}
```

This is a policy applied on every assignment. When a rebalance happens, the listener will re-seek the newly received partitions. Use this approach only if replaying or skipping backlog after every rebalance matches your business requirements.

If you only want to reset once when the consumer starts, manage first-assignment state per consumer thread. If you need a durable reset across restarts, change the consumer group's committed offsets using the administrative process in section 8.

## 5. Seeking to a Specific Offset

When you need to start from a specific position, use **seek(topic, partition, offset)**:

```java
@Override
public void onPartitionsAssigned(
        Map<TopicPartition, Long> assignments,
        ConsumerSeekCallback callback) {

    callback.seek("order-events", 0, 105L);
}
```

The example instructs the consumer to read partition 0 starting at offset 105. The offset must fall within the range Kafka still serves. If the offset is smaller than the beginning offset because data has expired, Kafka cannot recover deleted records; subsequent behavior depends on offset reset settings and consumer state.

Offsets must be specified individually per partition. Offset 105 of partition 0 does not represent the corresponding position in partition 1.

You can restrict seeking to a specific newly assigned partition:

```java
@Override
public void onPartitionsAssigned(
        Map<TopicPartition, Long> assignments,
        ConsumerSeekCallback callback) {

    TopicPartition target = new TopicPartition("order-events", 0);

    if (assignments.containsKey(target)) {
        callback.seek(target.topic(), target.partition(), 105L);
    }
}
```

Hard-coding offsets in application code is often difficult to operate. If the position varies by environment, load offsets from configuration, checkpoints, or administrative tools.

## 6. Distinguishing Seek from auto.offset.reset

**auto.offset.reset** is a Kafka consumer setting:

```yaml
spring:
  kafka:
    consumer:
      auto-offset-reset: earliest
```

Common values:

| Value | Behavior When No Valid Committed Offset Exists |
|---|---|
| **earliest** | Starts from the earliest retained beginning offset |
| **latest** | Starts from the current end offset |
| **none** | Throws an error if no valid committed offset is found |

**auto.offset.reset** applies only when the group has no valid committed offset or the committed offset falls outside the range still retained by brokers. It does not force a group that already has a valid committed offset back to the beginning or jump to the end.

Example:

- Group **billing-service** has committed offset 500.
- The application changes **auto-offset-reset** from **latest** to **earliest**.
- On restart, the consumer still resumes from offset 500 because the committed offset is valid.
- To re-read from the beginning offset, you must seek or reset the committed offset.

Changing **auto.offset.reset** is not a reliable way to replay data for an already active consumer group.

## 7. Seek Does Not Automatically Update Committed Offsets

This is the easiest point to confuse. When calling **seekToBeginning** or **seekToEnd**, the consumer changes its in-memory position. This operation does not automatically write a new committed offset to Kafka.

Example:

1. The group has committed offset 500.
2. The consumer is assigned a partition and seeks to beginning offset 100.
3. The consumer re-reads from offset 100.
4. If the application stops before a new committed offset is written, the next run can still start from offset 500.
5. If the listener processes records and the container commits new offsets per ack mode, the next run resumes from that newly committed offset.

The same applies when seeking to the end. If the consumer seeks to end offset 900 without processing any records and without a new commit, the old committed offset remains. After a restart, the group can revert to the old offset and read the backlog.

Spring Kafka manages commits according to container configuration and ack mode. Never call **consumer.commitSync()** directly from an arbitrary thread to make a seek durable; the Kafka consumer is not thread-safe, and commits must respect consumer thread ownership and container policies.

If the goal is to durably change the startup position of a consumer group, reset committed offsets using administrative tools while the group is stopped.

## 8. Resetting Committed Offsets with kafka-consumer-groups

When you need to change the read position persistently across restarts, you can use **kafka-consumer-groups.sh**.

First, inspect the group's status:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-service \
  --describe
```

Preview a reset to the beginning:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-service \
  --topic order-events \
  --reset-offsets \
  --to-earliest \
  --dry-run
```

If the result looks right, stop the consumer group and execute:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-service \
  --topic order-events \
  --reset-offsets \
  --to-earliest \
  --execute
```

To reset to the end, replace **--to-earliest** with **--to-latest**:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-service \
  --topic order-events \
  --reset-offsets \
  --to-latest \
  --dry-run
```

After verifying the dry-run output, re-run the command with **--execute**. You can target a single partition using the topic-partition syntax supported by the Kafka CLI, such as **--topic order-events:0**.

Operational notes:

- The consumer group must have no active consumers when resetting offsets.
- Always run **--dry-run** and verify expected offsets before **--execute**.
- Resetting offsets affects the next read of the specified group/partitions.
- Seeking to the beginning can generate a large volume of records to reprocess; seeking to the end can skip backlog.
- If resetting only specific partitions, specify the partitions explicitly to avoid unintended changes.

You can use the Kafka Admin API **alterConsumerGroupOffsets** to manage committed offsets from an administrative application. Check group state and ensure consumers are inactive during the modification. Do not use the administrative offset API in place of seek callbacks in a running listener.

## 9. Seeking During Rebalances and Concurrency Handling

A consumer group can rebalance when instances scale up/down, a consumer misses heartbeats, or partition assignments change. Partitions are revoked and reassigned to another consumer.

**onPartitionsAssigned** is called after partitions are assigned. This is the right moment to apply seek policies to newly received partitions.

Three things to watch out for:

1. **Seeking on every assignment** can repeat after a rebalance. If always seeking to the beginning, the consumer can replay already processed data.
2. **Seeking to the end on every assignment** can skip backlog newly assigned to the consumer after a rebalance.
3. **Concurrency** creates multiple consumer threads. Each thread has its own callback; do not store all callbacks in a single instance field and assume that callback represents every consumer.

If you need to store callbacks for seeking from another thread, store callbacks per consumer thread or partition assignment and update them when threads/assignments change. **ConsumerSeekCallback** marshals seek operations onto the consumer thread; when called from another thread, the seek request executes on the consumer thread on the appropriate poll cycle. Never call Kafka **Consumer.seek** directly from an external thread.

When seeking from another thread, handle cases where the callback has been replaced when the container restarts or concurrency changes. Manage the callback lifecycle instead of holding a stale reference indefinitely.

## 10. Testing Seek Callbacks

You can unit test seek policies by mocking **ConsumerSeekCallback**. You do not need to start a broker to verify that the listener requests seeks for the right partitions.

Example of a listener seeking to partition beginnings:

```java
import java.util.Map;

import org.apache.kafka.common.TopicPartition;
import org.junit.jupiter.api.Test;
import org.springframework.kafka.listener.ConsumerSeekAware.ConsumerSeekCallback;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class ReplayFromBeginningListenerTest {

    @Test
    void seeksAllAssignedPartitionsToBeginning() {
        ConsumerSeekCallback callback = mock(ConsumerSeekCallback.class);

        Map<TopicPartition, Long> assignments = Map.of(
            new TopicPartition("order-events", 0), 120L,
            new TopicPartition("order-events", 1), 450L
        );

        ReplayFromBeginningListener listener =
            new ReplayFromBeginningListener();

        listener.onPartitionsAssigned(assignments, callback);

        verify(callback).seekToBeginning(assignments.keySet());
    }
}
```

Place the test in the same package as the listener to reference **ReplayFromBeginningListener** directly. The listener constructor in the example takes no other dependencies. A similar test can be written for seeking to the end by verifying the call to **seekToEnd(assignments.keySet())**.

Unit tests verify that the listener issues the right seek command to the callback, not that the consumer actually reads records at the desired offset. For integration tests using Embedded Kafka, you should:

1. Create a topic with one or more partitions.
2. Send several records with specific keys/values.
3. Start the listener configured with the seek-to-beginning or seek-to-end policy.
4. Wait for the container to be assigned partitions via **ContainerTestUtils.waitForAssignment**.
5. Send verification records or observe received records via a queue.
6. Use finite timeouts and dedicated group IDs to avoid state dependencies from prior test runs.

When testing seek-to-beginning, ensure test records remain in the log. When testing seek-to-end, send new records after the listener finishes assignment and seek; new records must be received, while pre-seek backlog must be skipped in that run.

## 11. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Changed auto.offset.reset=earliest yet consumer still reads from old offset | Group still has valid committed offsets | Use ConsumerSeekAware or reset group offsets |
| Seeked to beginning yet did not read from offset 0 | Beginning offset increased due to retention or compaction | Check actual beginning offset |
| Seeked to end yet still read backlog | Seek called too late or not applied to required partitions | Seek inside onPartitionsAssigned and verify assignments |
| Reads from old committed offset after restart | Seek only changed in-memory position without a new commit | Reset committed offsets if durable change is needed |
| Rebalance causes records to be reprocessed | Seek-to-beginning policy re-applied when assignments change | Design seek per assignment and use idempotency |
| Consumer skips data after rebalance | Listener always seeks to end on every assignment | Use seek-to-end only when intentionally dropping backlog |
| Some partitions are not seeked | Wrong topic/partition specified or partition not in assignment | Check assignments.keySet() |
| Seek callback stops working after restart | Application held an old callback from a previous consumer thread | Receive new callbacks via registerSeekCallback |
| Duplicate processing after replay | Business logic is not idempotent | Use event IDs, deduplication, or safe replay |

## 12. Checklist Before Seeking

- Clearly identified whether to replay old data or skip backlog.
- Checked actual beginning/end offsets for each partition.
- Chose ConsumerSeekAware when seeking within the listener lifecycle.
- Used onPartitionsAssigned to seek newly assigned partitions.
- Understood that assignment callbacks may run again after rebalances.
- Did not confuse seek with committed offsets.
- If a durable reset is needed, stopped the consumer group and used offset reset tools.
- Used --dry-run before --execute.
- Prepared idempotency when replaying data.
- Tested both seek commands and actual record consumption behavior.

## 13. Key Takeaways

- Beginning offset is the lowest offset still retained, not necessarily 0.
- End offset is the next position after the last currently available record.
- seekToBeginning re-reads retained data; seekToEnd skips backlog and waits for new data.
- Spring Kafka provides ConsumerSeekAware and ConsumerSeekCallback to control read positions.
- onPartitionsAssigned is the right place to seek newly assigned partitions.
- auto.offset.reset only takes effect when there is no valid committed offset.
- Seek changes position in the running consumer without automatically committing the new position.
- To durably change committed offsets, reset the consumer group while the group is stopped.
- Rebalances can cause seek policies to re-apply; design replay and side effects safely.

Seek is a tool for controlling a consumer's read position. When you clearly understand beginning offsets, end offsets, committed offsets, and the partition assignment lifecycle, a Spring Kafka application can replay history or switch to reading only new events without confusing in-memory read state with the consumer group's saved state.


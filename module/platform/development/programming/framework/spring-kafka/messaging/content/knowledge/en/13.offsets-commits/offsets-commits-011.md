# Resetting Consumer Group Offsets

Kafka stores each consumer group's reading progress per topic-partition. Resetting offsets is the operation of changing a group's committed position so consumers re-read older data or skip a segment of data. This is an operational action that directly affects which records the application will process next.

With Spring Kafka, the listener container resumes from the group's committed offset. Therefore, to rewind or move a group to another position, you must change the group's committed offsets in a controlled manner. The Kafka CLI tool is a common option; the Kafka `AdminClient` also provides APIs to alter offsets programmatically.

## 1. What Do Consumer Group Offsets Represent?

Offsets are managed separately for each topic and partition pair. Consumer groups can have different progress on the same topic because each group stores its offsets independently.

Example:

```text
Topic orders
  Partition 0: record offsets 0, 1, 2, 3, 4, ...
  Partition 1: record offsets 0, 1, 2, 3, 4, ...

Group order-projection
  orders-0 -> committed offset 105
  orders-1 -> committed offset 82

Group order-audit
  orders-0 -> committed offset 70
  orders-1 -> committed offset 82
```

Two groups can read the same topic with independent progress. Resetting offsets for `order-projection` does not alter the offsets of `order-audit`.

**The committed offset is typically the next position to read**, not the offset of the last processed record. If a consumer processes record offset `104` successfully and commits `105`, the next read starts at `105`.

Kafka stores group offsets in the internal topic `__consumer_offsets`. Resetting offsets modifies the group's progress metadata; it does not delete records from the business topic.

## 2. When Should You Reset Offsets?

Common scenarios:

- **Replaying data:** re-running a consumer from the beginning or a historical checkpoint to rebuild a read model.
- **Fixing processing bugs:** the consumer processed a range of data incorrectly and needs to re-run after deploying a fix.
- **Skipping unneeded data:** moving the group to the end of the log to receive only newly produced records.
- **Testing or drills:** positioning a group at a known point to reproduce a scenario.
- **Incident recovery:** resetting reading progress after reconciling data and deciding on a resume point.

Before resetting, clarify whether the goal is to re-read or to skip. Resetting to a lower offset generally triggers replay; resetting to a higher offset can cause the group to skip unprocessed records.

## 3. Distinguishing Offset Resets from auto.offset.reset

These two mechanisms both relate to the starting read position, but they are not the same:

| Mechanism | When It Takes Effect | Impact |
|---|---|---|
| Resetting committed offsets | Operator or Admin API actively changes the group's saved offsets | Writes a new position for each topic-partition of the group |
| `auto.offset.reset` | Group has no valid committed offset, or saved offset is no longer within the readable log range | Selects a fallback starting position such as `earliest`, `latest`, or throws an error with `none` |

For example, changing a Spring Kafka setting from `latest` to `earliest` does not automatically rewind a group that already has valid committed offsets. The consumer still resumes from its committed offsets.

Conversely, resetting offsets with the Kafka CLI modifies the group's saved positions. Once the consumer restarts and joins the group, it reads from the new positions, provided those offsets remain valid for the log state.

`auto.offset.reset` is not an administrative tool for rewinding an active group. Use reset-offsets or the Admin API when intentionally modifying committed offsets.

## 4. Important Precondition: The Consumer Group Must Be Inactive

Before resetting with the Kafka CLI or `AdminClient`, stop all consumers participating in the target group. Kafka requires the group to have no active members for offset reset operations. If instances are still running, the reset command may be rejected; in other cases, an active consumer might continue committing offsets and overwrite the newly reset position.

A safe procedure typically follows these steps:

1. Identify the exact `group.id` and affected topic-partitions.
2. Stop the listener containers or scale down all instances of the service using that group.
3. Verify the group has no active consumer members.
4. Run the reset in preview mode and inspect the output for every partition.
5. Execute the reset after confirming the target positions.
6. Restart consumers and monitor lag and replayed or skipped records.

In a Spring Kafka application, containers can be stopped via `KafkaListenerEndpointRegistry` if all consumers for the group reside in that single instance. If the group is shared across multiple pods, services, or applications, stop all members across the cluster. Stopping one listener in one instance is insufficient if other consumers in the same group remain active.

## 5. Checking Group State Before Resetting

Use the Kafka CLI to inspect the consumer group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-projection
```

The output typically displays topic, partition, current offset, log end offset, lag, and consumer ID/host/client ID when members are active.

List groups:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list
```

`--list` only confirms the group exists; it does not prove the group is inactive. Use `--describe` output to verify consumer IDs/members; CLI versions supporting `--state` can display group state more explicitly.

Confirm that:

- The group name matches the service being adjusted.
- The topics and partitions in the output match the intended scope.
- Current offsets and log end offsets are recorded for comparison.
- The group has no active consumer members before executing the reset.
- No deployment or autoscaling process will automatically restart consumers during the operation.

## 6. Previewing Resets with --dry-run

Example resetting group `order-projection` to the earliest retained offset of topic `orders`:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group order-projection \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --dry-run
```

`--dry-run` computes and displays target offsets without writing changes to the group. Inspect the output for every partition before executing.

Once confirmed, re-run with `--execute`:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group order-projection \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --execute
```

Always run `--dry-run` first. Do not execute `--execute` merely because the command has no syntax error; verify the exact group, topic, partitions, and number of records that will be re-read or skipped.

Examples use `localhost:9092` for illustration. In real environments, substitute your bootstrap servers and add security configuration appropriate for your Kafka cluster.

## 7. Common Offset Reset Strategies

The Kafka CLI offers several ways to pick target positions. Option names can vary across Kafka versions; check `kafka-consumer-groups.sh --help` on your installed version before operating.

| Option | Meaning | Use Case |
|---|---|---|
| `--to-earliest` | Earliest offset still retained in the partition | Replay data still within retention |
| `--to-latest` | Log end offset at the time of reset | Skip existing data, read only new data |
| `--to-offset N` | Sets read position to offset `N` | Start from a known milestone |
| `--shift-by N` | Relative shift from the current committed offset | Step backward or forward by N offsets |
| `--to-datetime` | Selects offset based on timestamp | Replay from a point in time |
| `--by-duration` | Selects offset by stepping back a duration from now | Replay data from the last few hours or days |

### Reset to earliest

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group order-projection \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --dry-run
```

`earliest` is the earliest offset still retained, not necessarily `0`. If retention has deleted older data, resetting cannot restore those records.

### Reset to latest

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group order-projection \
  --topic orders \
  --reset-offsets \
  --to-latest \
  --dry-run
```

The group will start from the log end offset determined at reset time. Records existing in the log prior to that point are skipped by that group. Other groups are unaffected.

### Reset to a specific offset

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group order-projection \
  --topic orders \
  --reset-offsets \
  --to-offset 500 \
  --dry-run
```

Offset `500` is the next position the consumer will read. Before executing, check that the target offset falls within the partition's valid range and matches the business point to replay. Do not assume every offset number maps to a still-existing record; the log may have gaps due to compaction or retention.

### Relative shift with shift-by

Step back 100 offsets from the current position:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group order-projection \
  --topic orders \
  --reset-offsets \
  --shift-by -100 \
  --dry-run
```

Negative values shift backward to replay; positive values shift forward and can skip data. Inspect per-partition results because each partition has a different current offset. Do not apply a large shift without comparing earliest and end offsets.

### Reset by timestamp

Example choosing positions near the start of November 1, 2026:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group order-projection \
  --topic orders \
  --reset-offsets \
  --to-datetime 2026-11-01T00:00:00.000 \
  --dry-run
```

Kafka locates offsets based on record timestamps in each partition. Results depend on the timestamp type used by the topic/broker and retained data. Record timestamps are not always the business event creation time; if replaying by business time, verify what the record timestamp means first.

### Reset by recent duration

On Kafka versions supporting `--by-duration`, for example replaying roughly the last day:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group order-projection \
  --topic orders \
  --reset-offsets \
  --by-duration P1D \
  --dry-run
```

`P1D` is an ISO-8601 duration. Check that your CLI version supports this option and inspect resulting offsets before executing.

## 8. Reset Only Necessary Topics

You can specify a single topic with `--topic orders` as in the examples above. If a group subscribes to multiple topics, scoping the reset avoids accidentally resetting progress on other streams.

The Kafka CLI also supports resetting all topics for which the group has offsets via `--all-topics` on supporting versions:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group order-projection \
  --all-topics \
  --reset-offsets \
  --to-earliest \
  --dry-run
```

`--all-topics` has a broad scope and can affect multiple business streams. Use it only after listing and checking every topic-partition belonging to the group and obtaining proper operational approval. For routine operations, select specific topics explicitly.

If you only need to reset a few partitions, use the partition-selection syntax supported by your installed Kafka CLI or use `AdminClient` with an explicit `TopicPartition` map. Do not assume CLI syntax is identical across all versions; check the tool's help output before running.

## 9. Understanding Offset Results After a Reset

Suppose partition `orders-0` has:

```text
Current committed offset: 900
Log start offset:          100
Log end offset:           1200
```

Different choices have the following effects:

| Reset To | Next Position | Impact |
|---|---:|---|
| Earliest | 100 | Replays retained records from the earliest offset |
| Latest | 1200 | Skips existing records and waits for new records |
| Specific offset | 500 | Resumes from position 500 |
| Shift by -100 | 800 | Re-reads from position 800 up to before the old position |

These numbers are illustrative. Log start offset and log end offset change with retention, new writes, and administrative actions. For compacted topics, offsets may be non-contiguous because older records were removed.

The target offset is a read position, not a guaranteed count of records to be processed. To estimate replay volume, compare the target offset against the log end offset and inspect actual partition data.

## 10. Resetting Offsets with Kafka AdminClient

If an operational workflow needs automation, Kafka's `AdminClient` provides `alterConsumerGroupOffsets(...)`. This API takes a group ID and a map of `TopicPartition` to `OffsetAndMetadata`.

Example setting group `order-projection` to offset `500` on partition `0`:

```java
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;

public class ConsumerGroupOffsetReset {

    public void resetOrdersPartition() throws Exception {
        Properties properties = new Properties();
        properties.put(
                AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
                "localhost:9092");

        try (AdminClient admin = AdminClient.create(properties)) {
            Map<TopicPartition, OffsetAndMetadata> offsets = Map.of(
                    new TopicPartition("orders", 0),
                    new OffsetAndMetadata(500L)
            );

            admin.alterConsumerGroupOffsets("order-projection", offsets)
                    .all()
                    .get(10, TimeUnit.SECONDS);
        }
    }
}
```

`OffsetAndMetadata(500L)` sets the next position to read to `500`. The map contains only `orders-0`, so the example updates only that partition's offset; other partitions are untouched by this call.

The group must be inactive when altering offsets. The API does not provide a dry-run mode equivalent to the CLI; when automating, read current offsets, compute target offsets, log the plan, and require a confirmation step before calling `alterConsumerGroupOffsets`.

The example configures only the bootstrap server for illustration. In real environments, `AdminClient` requires proper security settings, credentials, and administrative permissions. Never hard-code secrets in source code.

## 11. Reading Committed Offsets Before Altering with AdminClient

Before writing new offsets, you can fetch current committed offsets to plan:

```java
Map<TopicPartition, OffsetAndMetadata> currentOffsets = admin
        .listConsumerGroupOffsets("order-projection")
        .partitionsToOffsetAndMetadata()
        .get(10, TimeUnit.SECONDS);

currentOffsets.forEach((partition, metadata) -> {
    System.out.printf(
            "%s-%d currentOffset=%d%n",
            partition.topic(),
            partition.partition(),
            metadata.offset());
});
```

You can combine `AdminClient` with `listOffsets(...)` to inspect log start/end offsets before planning a reset. Never pick an offset solely from the current committed offset; verify it falls within the readable log range and matches business goals.

An automated workflow should be split into two phases:

1. **Plan:** read group offsets and log bounds, calculate new positions, and output a per-partition report.
2. **Apply:** after approval, call `alterConsumerGroupOffsets` and read back to verify.

Never run the apply phase while consumers are still active. Keep an audit log recording requester, group, topic-partition, old offset, new offset, reason, and execution timestamp.

## 12. Offset Reset vs. Runtime Seek in Spring Kafka

Resetting group offsets changes the committed position stored in Kafka. `seek` changes the current read position of a running consumer. The two operations serve related purposes, but differ in scope and persistence.

Spring Kafka supports `ConsumerSeekAware` so listeners can control seeks within the consumer lifecycle—such as seeking to a specific offset or to the beginning of a partition when assigned. This mechanism suits intentional runtime operations on the consumer thread.

Conceptual example of seeking when partitions are assigned:

```java
import java.util.Map;

import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.listener.ConsumerSeekAware;
import org.springframework.kafka.listener.ConsumerSeekAware.ConsumerSeekCallback;
import org.springframework.stereotype.Component;

@Component
public class ReplayAwareListener implements ConsumerSeekAware {

    @Override
    public void registerSeekCallback(ConsumerSeekCallback callback) {
        // Store callback if seeking from another method is needed.
    }

    @Override
    public void onPartitionsAssigned(
            Map<TopicPartition, Long> assignments,
            ConsumerSeekCallback callback) {

        // Illustration only: seek to beginning of newly assigned partitions.
        // Do not enable this unconditionally in production.
        // callback.seekToBeginning(assignments.keySet());
    }
}
```

Seek changes the read position in the current consumer. If the group later commits an older offset or another consumer takes over the partition, the read position can revert to the committed offset. To durably change the group's progress, commit the new position or use reset-offsets/AdminClient while the group is inactive.

Do not place `seekToBeginning` unconditionally inside `onPartitionsAssigned` unless you intend to replay on every rebalance. This callback can be invoked multiple times over a consumer's lifecycle.

## 13. Impact on Business Processing When Replaying

Resetting offsets backward causes consumers to reprocess records that were already delivered. If the handler creates invoices, deducts inventory, sends emails, or calls external APIs, replay can duplicate side effects.

Before replaying, verify:

- Is the consumer idempotent by `eventId` or business key?
- Does the database have unique constraints, an inbox table, or deduplication?
- Do external service calls include idempotency keys?
- Can the read model be rebuilt from scratch, or must data be cleared/truncated first?
- Could retry topics, dead-letter topics, or other replay pipelines create duplicates?
- Can the replay run under a new group to avoid altering current production progress?

A safe approach for rebuilding a read model is creating a new consumer group, reading from the earliest retained offset, and writing to a new table/index. Once verified, switch the application to read from the new read model. This avoids changing offsets on the group serving live traffic, though it requires sufficient capacity and a data cutover plan.

## 14. Impact When Resetting Forward

Resetting to latest or an offset higher than current can skip unprocessed records. That is a decision to forfeit processing those records in that group; Kafka still retains records in the log until retention/compaction removes them, and other groups can still read them.

Before skipping data:

- Identify the exact offset range that will be skipped on each partition.
- Check whether any critical business events are waiting to be processed.
- Cross-check log end offsets and consumer lag.
- Confirm that the group can skip that segment or that the data was already processed via another workflow.
- Document the reason and who approved the operation.

Never use `--to-latest` as a fix for consumer lag without finding the root cause. If a consumer lags due to downstream errors, resetting to latest merely hides the problem by dropping the backlog.

## 15. Retention, Compaction, and Out-of-Range Offsets

Resetting cannot recover data that Kafka has already deleted due to retention. If the target offset is lower than the log start offset, the consumer cannot read records already removed from the log. Subsequent behavior may depend on `auto.offset.reset` if the offset becomes out of range.

For compacted topics, Kafka keeps the latest state per key and may delete older records during compaction. Non-contiguous offsets are normal; `--to-offset` chooses a position in the log rather than guaranteeing a record exists at that exact offset number.

If long-term replay beyond topic retention is required, you need another storage source such as backups, object storage, a source database, or an archive topic/store designed for that purpose. Resetting offsets only moves consumer progress; it does not extend retention.

## 16. Verifying After a Reset

After executing, read back the group offsets:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-projection
```

Verify:

1. Each topic-partition's current offset matches the target position.
2. No unexpected consumer member overwrote offsets during the operation.
3. Once consumers restart, partition assignment completes and listeners begin reading.
4. Lag changes in line with the replay or skip objective.
5. Records process correctly without unexpected duplicate side effects.
6. No `OffsetOutOfRange`, deserialization, or downstream errors occur from historical data.

If resetting to earliest, lag typically rises because the group must re-read the backlog. If resetting to latest, lag may drop near 0 at reset time. These are observational signals and do not replace business verification.

## 17. Common Errors

**Group is still active:** stop all consumers sharing the group and re-check status before resetting.

**Resetting the wrong group:** verify `group.id` across Spring Kafka configuration, CLI commands, and deployment environments.

**Resetting the wrong topic or partition:** specify `--topic` explicitly and read dry-run output carefully before executing.

**Assuming `auto.offset.reset=earliest` triggers replay:** this setting applies only when no valid committed offset exists. Use an intentional offset reset.

**Reset succeeded yet consumer reads elsewhere:** check if an active consumer overwrote commits, a listener performs runtime seeks, the group has other members, or the target offset is no longer valid.

**Resetting to an old offset whose data passed retention:** Kafka cannot return deleted records. Use backups or an authoritative data source.

**Replay creates duplicate data:** implement idempotency/deduplication and verify external side effects.

**Using `--all-topics` unintentionally:** restrict scope with explicit `--topic` and review dry-run before executing.

**CLI does not support an option:** check `--help` and Kafka CLI version; some time-based reset options differ across versions.

**AdminClient fails to alter offsets:** verify the group is inactive, administrative ACL permissions exist, and check exceptions returned from the API future.

## 18. Offset Reset Operational Checklist

- Clearly defined whether the goal is to replay or skip backlog.
- Verified the exact cluster, group ID, topic, and partitions.
- Recorded current offsets, log start offsets, and log end offsets.
- Stopped all consumer members of the group and prevented autoscaling from restarting them during the operation.
- Selected the appropriate reset strategy: earliest, latest, specific offset, shift, or timestamp.
- Ran `--dry-run` and verified per-partition results.
- Used `--execute` only after target offsets were confirmed.
- If using AdminClient, included a plan/approval step before `alterConsumerGroupOffsets`.
- Ensured handlers are idempotent before replaying data.
- Verified committed offsets and consumer behavior after restarting.
- Monitored lag, listener errors, and business side effects afterward.
- Saved an audit log for the reset operation.

Resetting offsets is how you adjust a consumer group's reading progress per partition. Doing it safely requires stopping the group, previewing target offsets, applying the exact scope, and verifying after restart. In particular, evaluate the business impact of replaying or skipping because Kafka manages read positions while idempotency and correctness of side effects remain the application's responsibility.

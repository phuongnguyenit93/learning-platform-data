# Configuring cleanup.policy

Kafka stores records in partitions as an append-only log. Once a record has been written, the broker does not modify that record directly; data cleanup runs in the background according to the topic's cleanup policy. The **cleanup.policy** topic property determines whether Kafka retains the log by time/size, retains the latest value per key, or combines both approaches.

Choosing the right cleanup policy is a decision about data semantics. Topics storing event history where every record must be retained typically use `delete`. Topics representing the latest state of each entity usually fit `compact`. Some topics that need both the latest state and an age limit on data can use `compact,delete`.

## Learning Objectives

After this lesson, you can:

- Explain the purpose and valid values of `cleanup.policy`.
- Distinguish between `delete`, `compact`, and `compact,delete`.
- Describe log compaction, keys, tombstones, and how Kafka handles deleted records.
- Understand why compaction runs asynchronously and does not delete records immediately upon a new write.
- Select related settings such as `retention.ms`, `retention.bytes`, `delete.retention.ms`, and `min.compaction.lag.ms`.
- Create and modify cleanup policies using the Kafka CLI or Spring Kafka Admin.
- Design keys and partitions appropriately so compaction reflects the intended business state.
- Test, observe, and troubleshoot common configuration errors.

## 1. cleanup.policy Determines How Logs Are Cleaned Up

Each topic has a `cleanup.policy` configuration. The main values are:

| Value | How Kafka Cleans the Log | Suitable Use Cases |
|---|---|---|
| `delete` | Deletes log segments when data exceeds time-based or size-based retention limits | Event logs, audit logs, telemetry with a retention window |
| `compact` | Retains the latest value per key in each partition; older records with the same key may be removed via compaction | Topics storing current state, changelogs, cache state |
| `compact,delete` | Both compacts by key and applies retention to delete old segments | Topics needing the latest state within a bounded storage window |

In topic configuration, two policies can be declared as a comma-separated list. For example: `compact,delete`.

If not explicitly specified on the topic, Kafka uses the default value from the broker. Broker configuration typically sets `log.cleanup.policy` to `delete` by default. In operations, inspect the topic's effective configuration rather than inferring from another environment's default settings.

Important point: `cleanup.policy` does not decide the order in which consumers read records. It determines whether older data is retained or eligible for removal from the log after being written.

## 2. Delete Policy: Retaining Logs by Retention

With `delete`, Kafka keeps segments according to time or size limits. Two commonly used settings are:

- `retention.ms`: maximum age of data under the retention policy.
- `retention.bytes`: maximum log size per partition under the retention policy.

When a segment is old enough or the log exceeds the size threshold, Kafka marks eligible segments for deletion. Deletion happens at the segment level and carries operational latency; `retention.ms` should not be treated as an exact timer for individual records.

Example of a topic retaining order events for 14 days:

~~~properties
cleanup.policy=delete
retention.ms=1209600000
~~~

Example creating the topic via Kafka CLI:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic order-events \
  --partitions 6 \
  --replication-factor 3 \
  --config cleanup.policy=delete \
  --config retention.ms=1209600000
~~~

`delete` is appropriate when record history matters within the retention window. Once segments expire, a consumer reading from the beginning will no longer see deleted data. If a consumer is offline longer than retention, it may encounter an offset out-of-range error and must be handled via reset policy or an appropriate recovery procedure.

Retention does not replace backups. If data must be retained long-term for compliance or recovery requirements, design a dedicated storage system rather than relying solely on a Kafka topic.

## 3. Compact Policy: Retaining the Latest State per Key

Log compaction retains the latest record per key in each partition. Kafka does not need to keep every intermediate update when the topic's goal is to reconstruct current state.

Example of a `customer-state` topic receiving updates:

~~~text
offset  key       value
------  --------  ------------------
0       customer-1  name=An
1       customer-2  name=Binh
2       customer-1  name=An, city=Hanoi
3       customer-3  name=Chi
4       customer-1  name=An, city=DaNang
5       customer-2  name=Binh, tier=Gold
~~~

After compaction completes on eligible segments, Kafka can retain the latest state for each key:

~~~text
offset  key         value
------  ----------  -----------------------------
3       customer-3  name=Chi
4       customer-1  name=An, city=DaNang
5       customer-2  name=Binh, tier=Gold
~~~

This illustrates the logical outcome. In the physical log, offsets are not renumbered sequentially from 0 and gaps can appear where older records were removed. Kafka preserves original offset semantics so consumer groups can continue reading from their committed positions.

### Compaction Applies Only Within Each Partition

The cleaner compares keys within the scope of a single partition. Kafka does not perform a global key merge across all partitions of a topic.

Therefore:

- The same key must be routed deterministically to the same partition if compaction is expected to preserve a single state for that key.
- Producers typically use a business key, such as `customerId` or `accountId`.
- Increasing the partition count can change the key-to-partition mapping. Old and new records for the same key may land in two different partitions, preventing compaction from deduplicating across them.
- If a producer sends keyless records, compaction cannot use a key to identify state and those records are not compacted to retain the latest value.

Example sending a keyed record in Spring Kafka:

~~~java
kafkaTemplate.send("customer-state", customerId, customerState);
~~~

If the key is `null`, the application has omitted the identifier that compaction relies on. Define the key before selecting `compact`.

### Compaction Does Not Remove Records Immediately

The Kafka log cleaner runs in the background. New records can temporarily coexist with older versions. An active segment is normally not compacted until it is rolled and becomes eligible. Compaction also depends on the amount of uncompacted data and cleaner resources.

Therefore, consumers reading a compacted topic must not assume that at every moment the log holds only one record per key. While compaction has not finished running, a consumer can still read multiple versions of the same key.

## 4. Tombstones: Representing Key Deletion

In a compacted topic, an application represents deleting a key's state by sending a record with a key and a `null` value. Such a record is called a **tombstone**.

Example:

~~~java
// Delete the current state of customer-42 in the compacted topic.
kafkaTemplate.send("customer-state", "customer-42", null);
~~~

A tombstone does not mean Kafka immediately deletes all older records for that key. It marks that the key's current state has been deleted. When the cleaner processes the log, older versions of the key can be removed along with the tombstone according to the compaction lifecycle.

### delete.retention.ms

`delete.retention.ms` defines how long a tombstone is retained so consumers have an opportunity to observe the deletion when re-reading the compacted log. Once the tombstone becomes eligible to expire and the cleaner processes it, the tombstone can be removed.

This setting is especially important for consumers using a compacted topic as a changelog to rebuild a state store. If a consumer replays from the beginning too slowly or stays offline longer than the tombstone window, it might miss the deletion marker while reading stale data unintentionally.

Example:

~~~properties
cleanup.policy=compact
delete.retention.ms=86400000
~~~

The value above illustrates a one-day window. Choose a window large enough relative to the maximum time a consumer needs to rebuild state or catch up on the log.

Tombstones can also appear in state-update streams. Consumers must distinguish a `null` value representing deletion from a valid JSON payload containing empty fields. Deserializers and listeners must preserve this `null` semantics.

## 5. How Do compact and compact,delete Differ?

Both configurations involve compaction, while `compact,delete` adds time-based or size-based retention limits.

| Criterion | `compact` | `compact,delete` |
|---|---|---|
| Retains latest version per key | Yes | Yes |
| Deletes segments per `retention.ms`/`retention.bytes` | Does not apply topic delete policy | Yes |
| Older data with no newer key | Can persist until compaction becomes eligible | Can be deleted when segments expire |
| Tombstones | Yes, per `delete.retention.ms` | Yes, also affected by retention |
| Typical goal | Changelog/state topic needing reconstruction of latest state | State topic only needing storage within a time/size window |

With `compact`, Kafka can keep the latest record per key in the log long-term unless the topic is deleted or other administrative configuration/actions occur. With `compact,delete`, old segments can still be deleted by retention even if compaction had preserved some state inside those segments.

Do not pick `compact,delete` merely to "keep things tidier." If consumers need to rebuild full current state across all keys, ensure retention does not delete the last needed record before state is snapshotted or persisted to another storage system.

Example:

~~~properties
cleanup.policy=compact,delete
retention.ms=2592000000
delete.retention.ms=86400000
~~~

This example retains logs under a 30-day retention policy and uses a one-day tombstone window. Actual values must be grounded in recovery requirements and consumer speed.

## 6. Related Compaction Configurations

`cleanup.policy` is the switch selecting the policy. The following properties control when and how the cleaner runs.

| Property | Meaning |
|---|---|
| `min.cleanable.dirty.ratio` | Minimum ratio of uncompacted data required for a log to become eligible for selection by the cleaner under this threshold |
| `min.compaction.lag.ms` | Minimum time a record must remain in the log before it can be compacted |
| `max.compaction.lag.ms` | Target maximum delay before eligible records are considered for compaction |
| `delete.retention.ms` | Duration tombstones are retained so consumers can observe deletions |
| `segment.ms` | Maximum time before a log segment is rolled based on time |
| `segment.bytes` | Target segment size before rolling based on size |

### min.cleanable.dirty.ratio

The cleaner evaluates the uncompacted portion of the log (dirty log) against the total log. Once the ratio reaches `min.cleanable.dirty.ratio`, the log can become eligible for cleaner processing, depending on load and cleaner resources.

- Lower values typically trigger compaction more frequently, increasing I/O and cleaner activity.
- Higher values reduce how often the cleaner runs, though older versions may remain longer.

Do not treat this ratio as a guarantee that compaction starts at the exact instant the ratio is crossed. The cleaner must also have available resources and segments must be eligible.

### min.compaction.lag.ms and max.compaction.lag.ms

`min.compaction.lag.ms` keeps records in the log for at least a minimum period before compaction can remove older versions. This is helpful when consumers need a window to read recent changes.

`max.compaction.lag.ms` sets a target upper delay bound for eligible records to be considered for compaction. This is not a strict deadline guaranteeing the cleaner finishes every operation; broker load, segment state, and cleaner capacity still influence actual timing.

Example topic needing to keep changes for at least 10 minutes before compacting:

~~~properties
cleanup.policy=compact
min.compaction.lag.ms=600000
~~~

### Broker Log Cleaner

Compaction requires the log cleaner to be active on brokers. Related broker settings include `log.cleaner.enable` and parameters governing cleaner resources. If the cleaner is disabled or lacks sufficient resources, compacted topics still accept records, while older versions can persist longer than expected.

In operations, check both topic config and broker config. Merely setting `cleanup.policy=compact` does not mean all older records are immediately cleaned up.

## 7. Configuring Topics with Kafka CLI

You can create a topic with a cleanup policy upfront:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic customer-state \
  --partitions 6 \
  --replication-factor 3 \
  --config cleanup.policy=compact \
  --config delete.retention.ms=86400000 \
  --config min.compaction.lag.ms=60000
~~~

To update the configuration of an existing topic, use `kafka-configs.sh`:

~~~bash
bin/kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name customer-state \
  --alter \
  --add-config cleanup.policy=compact
~~~

Check the effective configuration:

~~~bash
bin/kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name customer-state \
  --describe
~~~

To switch from `compact` to `compact,delete`:

~~~bash
bin/kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name customer-state \
  --alter \
  --add-config cleanup.policy=compact,delete
~~~

Script names may end in `.sh` or `.bat` depending on the operating system and Kafka distribution. With modern KRaft clusters, use `--bootstrap-server`; no ZooKeeper argument is needed.

When removing a configuration override, use `--delete-config` with the exact config name so the topic reverts to the broker default. Confirm current settings before deleting an override, as inherited defaults may differ across environments.

## 8. Declaring Topics with Spring Kafka

Spring Kafka can create topics at startup through `KafkaAdmin` and `NewTopic` beans. Example:

~~~java
@Configuration
public class TopicConfiguration {

    @Bean
    public NewTopic customerStateTopic() {
        return TopicBuilder.name("customer-state")
                .partitions(6)
                .replicas(3)
                .config(TopicConfig.CLEANUP_POLICY_CONFIG,
                        TopicConfig.CLEANUP_POLICY_COMPACT)
                .config(TopicConfig.DELETE_RETENTION_MS_CONFIG, "86400000")
                .config(TopicConfig.MIN_COMPACTION_LAG_MS_CONFIG, "60000")
                .build();
    }
}
~~~

The example above declares a compacted topic along with related settings. `KafkaAdmin` must be configured to connect to the target cluster, and the application principal must have permission to create topics.

One distinction to keep clear: a `NewTopic` bean mainly describes the topic to create. Do not assume that changing properties in the bean will always alter the configuration of an existing topic. For existing topics, use a topic configuration alter mechanism such as Kafka CLI or `AdminClient` following your system's governance workflow.

If the application declares `NewTopic` across multiple environments, externalize partitions, replication factor, and cleanup policy per environment rather than hard-coding values unsuitable for every cluster.

## 9. Designing Compacted Topics for Business State

A compacted topic is commonly used as a changelog of current state. Each record carries a key identifying the entity and a value containing the latest state.

Example:

| Key | Value | Meaning |
|---|---|---|
| `account-100` | `balance=500` | Latest balance of the account |
| `account-101` | `balance=120` | Latest balance of the account |
| `account-100` | `balance=450` | New state update for `account-100` |
| `account-101` | `null` | Deletes state of `account-101` |

Design principles:

1. Use a stable, unique key per business entity.
2. Publish a full state snapshot if consumers need to build state independently; if values are deltas only, consumers must apply the remaining sequence of changes per the contract.
3. Send a keyed tombstone when deleting an entity.
4. Keep the same key in the same partition; evaluate impacts before increasing partition counts.
5. Set `delete.retention.ms` long enough for consumers to reinitialize or catch up on data.
6. Do not use `compact` if the business requires preserving every intermediate event as an immutable history.

Compaction does not turn Kafka into an arbitrary-query key-value database. Consumers still read logs sequentially by partition; for fast key lookups, applications can build a state store or use an appropriate storage engine.

## 10. When Should You Not Use compact?

Do not use `compact` for topics where every event has independent historical value.

For example, an audit log that must retain all actions:

~~~text
UserRegistered
EmailChanged
PasswordReset
RoleGranted
RoleRevoked
~~~

If all records use the same `userId` as the key and the topic is compacted, Kafka can discard intermediate events, retaining only the latest event per key after compaction. That breaks the completeness of the audit trail.

Similarly, event sourcing usually requires retaining every event to reconstruct aggregate state. Compaction can break that goal. Use `delete` with an appropriate retention window, or design a separate snapshot topic alongside the event log.

A common architectural pattern:

- An `order-events` topic uses `delete` to preserve event history for a defined period.
- An `order-state` topic uses `compact` to retain the latest state of each order.
- A consumer updates `order-state` from `order-events` through a controlled process.

The two topics serve different purposes, so they can use different cleanup policies.

## 11. Impact on Consumers and Offsets

Compaction removes older records without renumbering the offsets of remaining records. Consequently, a consumer may read:

~~~text
offset 10 -> key A, value v3
offset 14 -> key B, value v2
offset 19 -> key C, value v5
~~~

Offset gaps are normal in compacted topics. Do not assume the next offset always equals the current offset plus one, or that offset differences accurately reflect the number of remaining records.

Consumer groups commit offsets corresponding to the next position to read. After compaction, a consumer replaying from the beginning may encounter gaps where old records were removed. This is expected cleanup behavior, not unintended data loss.

With compacted topics, consumers should:

- Tolerate non-contiguous offsets.
- Handle multiple versions of the same key when compaction has not yet completed.
- Treat tombstones as state deletions.
- Not depend on ordering across partitions.
- Design state recovery around retention and `delete.retention.ms` policies.

Compaction does not alter the offsets of remaining records, so active consumers can continue using committed offsets. However, consumers offline for long periods must still account for retention, tombstones, and the possibility that older offsets fall before the log start offset.

## 12. Testing and Observability

You can test a compacted topic by creating one with `cleanup.policy=compact`, sending multiple records with the same key, waiting for segments to roll and the cleaner to run, and then reading from the beginning to verify old versions were removed.

Test scenarios should cover:

- Sending multiple values for the same key and verifying the final state is retained after compaction.
- Sending different keys and verifying each key keeps its latest state.
- Sending a tombstone and verifying consumers process `null` values as deletions.
- Reading the compacted topic before the cleaner runs to verify the application tolerates multiple versions of the same key.
- Reinitializing a state consumer and testing the `delete.retention.ms` window.
- Testing `compact,delete` with retention to confirm old data can be removed per policy.
- Verifying consumers do not assume contiguous offsets.

Do not write tests that rely on a fixed compaction timestamp. The cleaner runs asynchronously, and segment/dirty-ratio conditions affect when it executes. Integration tests should synchronize on observable state with generous timeouts rather than using a short sleep and concluding compaction failed.

Useful operational metrics:

- Log size and segment count per topic/partition.
- Write rate and log cleaner I/O rate.
- Cleaner backlog, compaction duration, and broker resources.
- Consumer lag and state initialization duration.
- Tombstone count and age during consumer reinitialization flows.
- Retention and log start offset per partition.

If a topic's disk usage grows continuously, check whether the cleaner is running, whether the dirty ratio reaches the threshold, whether segments are rolling, and whether brokers have sufficient cleaner resources.

## 13. Common Configuration Mistakes

**Using compact for audit logs.** Compaction discards older versions of the same key, losing intermediate event history. Choose `delete` when every event must be kept.

**Sending keyless records to a compacted topic.** Kafka has no identifier to preserve the latest value per entity. Producers must supply stable keys.

**Assuming tombstones delete data immediately.** Tombstones are retained for a period and compaction runs in the background. Consumers must tolerate older data still existing before the cleaner finishes.

**Setting delete.retention.ms too short.** Slow-reinitializing consumers can miss tombstones and reconstruct stale state. Choose a duration covering the recovery window.

**Increasing partitions without evaluating key routing.** The same key may map to a different partition after partition count changes; compaction does not merge keys across partitions.

**Choosing compact,delete with overly short retention.** Segments holding a key's latest state may be deleted by retention, leaving consumers unable to rebuild full state.

**Assuming NewTopic always updates existing topics.** Topic creation and modifying existing topic configurations must be governed separately.

## 14. Cleanup Policy Selection Checklist

- [ ] Does the topic store event history or latest state?
- [ ] If using `compact`, do all business records have a stable key?
- [ ] Is the same key routed to the same partition?
- [ ] Do consumers handle tombstones and multiple versions of the same key?
- [ ] Is `delete.retention.ms` long enough for state reinitialization time?
- [ ] Is `min.compaction.lag.ms` needed so consumers can read recent changes?
- [ ] Do `max.compaction.lag.ms` and `min.cleanable.dirty.ratio` match operational goals?
- [ ] Is the broker log cleaner enabled and adequately resourced?
- [ ] If using `compact,delete`, do `retention.ms`/`retention.bytes` preserve enough data for recovery?
- [ ] Have asynchronous compaction, non-contiguous offsets, and tombstones been tested?

## Conclusion

`cleanup.policy` controls whether Kafka maintains logs by retention, by the latest state per key, or a combination of both. `delete` suits event history with a retention window; `compact` suits changelog/state topics needing the latest state; `compact,delete` combines compaction with retention limits. Compaction runs in the background, operates within each partition, and relies on keys; tombstones represent deletions and must be kept long enough for consumers to observe them. In Spring Kafka, choose keys and cleanup policies according to data semantics, configure topics explicitly, and test consumers with multiple record versions, tombstones, and non-contiguous offsets.


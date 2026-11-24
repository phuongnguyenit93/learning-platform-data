# auto.offset.reset

## 1. Role of auto.offset.reset

`auto.offset.reset` is a Kafka consumer configuration that determines where a consumer starts reading when Kafka has no valid committed offset for a partition. In Spring Kafka, this setting is typically declared via `spring.kafka.consumer.auto-offset-reset`.

This setting is used only when the consumer must determine an initial read position or recover a read position because the current offset is no longer valid. It is not an offset deletion command, not an offset commit mechanism, and it does not automatically rewind a consumer group to the start of a topic on every application restart.

Common values:

- `earliest`: start from the earliest offset currently retained in the partition.
- `latest`: start from the end of the log at the moment the consumer needs to determine its read position.
- `none`: do not pick a position automatically; throw an error if no valid offset is found.

Some newer Kafka client versions also support duration-based policies such as `by_duration:<duration>`. Feature availability and syntax depend on the Kafka client version; check the documentation for your exact version before using it.

In operations, this choice directly determines whether a consumer group re-reads historical data, skips historical data, or halts to require operator intervention on offsets.

## 2. Understanding Committed Offsets Before Choosing a Policy

### 2.1. An Offset Is the Next Read Position

Each partition has its own log and monotonically increasing offsets. A consumer group stores its own committed offset per topic-partition in Kafka, typically managed through the internal topic `__consumer_offsets`.

The committed offset represents the next position the group will read. For example, if the group has processed record offset 14 and committed offset 15, the next read starts at offset 15.

~~~text
Partition orders-0

Offset:       10   11   12   13   14   15   16   17
Record:       A    B    C    D    E    F    G    H
                                      ^
                         committed offset = 15
                         next record to be read: 15
~~~

Because the committed offset is the next position, it is not the offset of the last processed record. This distinction matters when investigating lag, resetting offsets, or comparing against log start/end offsets.

### 2.2. Offsets Belong to a Consumer Group

Kafka stores progress keyed by the combination of:

- Consumer group ID.
- Topic.
- Partition.

Two different groups can read the same topic from different positions. For instance, `billing-service` may have read up to offset 500 of `orders-0`, while `analytics-service` has only read up to offset 120.

If you change the application's `group.id`, Kafka treats it as a different group. The new group typically has no committed offset yet, so `auto.offset.reset` is used to determine the starting position. This is why a group ID change can cause an application to re-read a large volume of data or start from the end of the log.

Do not share a group ID between two processing streams that need independent progress. Conversely, instances of the same service typically share a group ID to split partitions and coordinate progress.

## 3. When Is auto.offset.reset Applied?

There are three main situations.

### 3.1. The Group Has No Committed Offset Yet

When a consumer group reads a topic for the first time, or the group has never committed an offset for a partition, Kafka has no saved position to resume from. The consumer uses `auto.offset.reset` to pick a starting position.

Examples:

- A new group reads the `orders` topic.
- An existing group is switched to a new group ID.
- The application starts reading a new topic.
- A new partition is added to a topic and the group has no offset for that partition yet.

If set to `earliest`, the consumer reads from the earliest retained data. If set to `latest`, the consumer starts at the end of the log and waits for new records. If set to `none`, the consumer reports an error because no offset is available.

### 3.2. The Committed Offset Is No Longer in the Log

Suppose a group committed offset 20, but the topic has retention configured and the broker deleted older records, raising the partition's log start offset to 30. The consumer can no longer resume from offset 20 because the data at that position no longer exists.

Kafka reports an offset out-of-range condition. The `auto.offset.reset` policy is used to determine the new position:

- `earliest`: move to the current log start offset, e.g., 30.
- `latest`: move to the current log end offset.
- `none`: raise an error for the application or operator to decide.

This means `earliest` does not guarantee reading from offset 0. If retention deleted the head of the log, the earliest available offset may be 30, 500, or another value. For compacted topics, the log can also have offset gaps where compaction removed older records.

### 3.3. Offset Invalidated After Partition Data Changes

Abnormal events such as truncation or log state changes can leave the committed offset past the current log end offset. When the consumer cannot use the stored offset, the reset policy can also be applied.

Never treat automatic resets as a fix for every data incident. If an offset unexpectedly goes out of range, inspect leader/replica state, log truncation, retention, and operational history before accepting the new position.

### 3.4. When Is the Setting Not Applied?

If the group already has a valid committed offset, the consumer resumes from that offset. For example, if a group already committed offset 150, changing `auto.offset.reset` from `latest` to `earliest` does not make the consumer go back to the start of the topic; it still resumes from offset 150.

If the application calls `seek()` or an explicit read-position control mechanism, the specified position can override the automatic decision. The reset setting is primarily a fallback policy when the consumer lacks a valid initial position.

## 4. Comparing earliest, latest, and none

| Value | Starting Position | Common Impact | Best Suited For |
|---|---|---|---|
| `earliest` | Earliest retained offset | May replay historical data and create high startup load | New consumers needing to build state from history |
| `latest` | End of log at reset time | Skips existing historical data, receiving only new data after start position | Streams only interested in newly arriving events |
| `none` | No automatic selection | Consumer errors if a valid offset is missing | Detecting misconfiguration or missing offset provisioning |

### 4.1. earliest: Prioritizing Retained History

`earliest` instructs the consumer to start from the earliest position the broker still retains in the partition. This is usually the right choice for a new consumer group that must read all surviving historical data, such as building a read model or syncing data from an event log.

However, `earliest` is not a replay-on-every-restart mechanism. If the group has already committed an offset, the consumer still resumes from that offset. It only starts from the beginning of the retained log when no valid offset exists.

The operational risk is that a new group may have to process a huge backlog of records. If downstream has throughput limits, consumer lag can spike and impact the system. Estimate data volume, processing speed, retention, and database capacity before creating a new group with `earliest`.

### 4.2. latest: Receiving Only Data After the Current Position

`latest` sets the initial position at the end of the log at reset time. Records existing prior to that position are not read by the new group.

This fits streams that only care about new events, such as a consumer ingesting fresh telemetry without needing history. For payments, orders, or state updates requiring complete data, using `latest` on a group without an offset can forfeit processing older retained events.

`latest` also does not mean the consumer always jumps to the end of the log. Once the group has a valid committed offset, the consumer resumes from the committed offset and reads subsequent records normally.

When a group receives new partitions or loses its offsets, `latest` can cause existing records on those partitions to go unread. Evaluate carefully when expanding topic partition counts or changing group IDs.

### 4.3. none: Requiring a Pre-Supplied Read Position

`none` instructs Kafka not to choose an offset automatically if no valid committed offset exists. The consumer raises an error, typically `NoOffsetForPartitionException` when no initial offset is present.

This policy is useful when deployment procedures require a group to be initialized or have offsets pre-set before running. It catches a misconfigured new group ID early rather than silently reading from the start or skipping old data.

In return, if operations adds partitions without setting offsets for the new partitions, or offsets expire after long group inactivity, the consumer can stop with an error. Maintain an offset provisioning procedure and monitor initialization failures.

## 5. Illustrative Example of Offset Selection

Suppose partition `orders-0` has log start offset 40 and log end offset 100. Group `billing-service` has no committed offset for this partition yet.

~~~text
Log start                                                   Log end
    40  41  42  43  44  ...  96  97  98  99
     |                               |
     +-- earliest                    +-- latest
~~~

| Configuration | Consumer Start Position | Records Read Next |
|---|---:|---|
| `earliest` | 40 | 40, 41, 42, ... |
| `latest` | 100 | New records written from position 100 onward |
| `none` | No automatic position | Throws error because group has no offset |

If the group already committed offset 75, none of the three settings alters that valid read position. The consumer resumes at 75.

If retention deletes records until the log start offset rises to 80 while the group still holds committed offset 75, offset 75 is no longer available. At that point:

- `earliest` moves to 80.
- `latest` moves to the current log end.
- `none` throws an error.

This is the core takeaway when reading configuration: the policy only intervenes when initializing or recovering a read position, never replacing a valid committed offset.

## 6. Configuration in Spring Boot and Spring Kafka

### 6.1. Declaring via application.yml

Example of a consumer group that needs to process retained historical data:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: billing-service
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.events
    listener:
      ack-mode: record
~~~

The Spring Boot property `auto-offset-reset` maps to the Kafka client property `auto.offset.reset`. The value can be declared as `earliest`, `latest`, or `none` per application policy.

In this example:

- `group-id` identifies the namespace storing read progress.
- `auto-offset-reset` governs initialization when the group lacks a valid offset.
- `enable-auto-commit: false` lets the Spring listener container manage commits per acknowledgment mode.
- `ack-mode: record` requires committing progress record by record after successful listener processing.

`auto-offset-reset` and `enable-auto-commit` solve two different problems. One chooses the initial position; the other controls how offsets are committed during processing.

### 6.2. Declaring via properties

If using `application.properties`:

~~~properties
spring.kafka.bootstrap-servers=localhost:9092
spring.kafka.consumer.group-id=billing-service
spring.kafka.consumer.auto-offset-reset=earliest
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.listener.ack-mode=record
~~~

If configuring the Kafka consumer factory directly, the Kafka client key is `auto.offset.reset`:

~~~java
Map<String, Object> consumerProperties = new HashMap<>();

consumerProperties.put(
    ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
    "localhost:9092"
);
consumerProperties.put(
    ConsumerConfig.GROUP_ID_CONFIG,
    "billing-service"
);
consumerProperties.put(
    ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
    "earliest"
);
consumerProperties.put(
    ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
    false
);

ConsumerFactory<String, OrderCreated> consumerFactory =
    new DefaultKafkaConsumerFactory<>(consumerProperties);
~~~

`ConsumerConfig.AUTO_OFFSET_RESET_CONFIG` avoids property name typos in Java configuration. Ensure the consumer factory is actually wired into the listener container; creating a factory without attaching it to the container will not change consumer behavior.

### 6.3. Overriding Group ID on @KafkaListener

A listener can declare its group ID directly:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing-service"
)
public void onOrderCreated(OrderCreated event) {
    billingService.process(event);
}
~~~

When the annotation specifies `groupId`, the listener uses that group per annotation settings. If multiple listeners have different group IDs, each group maintains independent committed offsets and `auto.offset.reset` applies separately per group-partition when needed.

Before changing a group ID, confirm whether the change is intentional or a configuration error. A typo in a group ID can create a brand-new group and cause `earliest` to replay history or `latest` to skip retained history.

## 7. How Does auto.offset.reset Differ from Offset Commits?

Two mechanisms are frequently confused:

| Mechanism | Question It Answers | Example |
|---|---|---|
| `auto.offset.reset` | If no valid read position exists, where should reading start? | `earliest` or `latest` |
| Offset commit | How far has the group processed and where should it read next? | Commit offset 101 so the next read starts at 101 |
| `enable.auto.commit` | Does the Kafka client periodically auto-commit offsets? | `false` so the container coordinates commits |
| Acknowledgment mode | Does the Spring listener container commit per record, batch, or manual acknowledge? | `RECORD`, `BATCH`, `MANUAL` |

For example, a listener processes record offset 25 and commits offset 26. When the application restarts, the consumer resumes at 26 even if `auto.offset.reset=earliest` is configured. It does not return to offset 0 or the log start offset.

If a listener completes side effects successfully but the application stops before committing, the record may be redelivered. That is an issue of delivery semantics and idempotency, not a bug in `auto.offset.reset`.

Conversely, if a committed offset is deleted from the log by retention, the consumer cannot resume from the old position. Only then does the reset policy decide how to recover.

## 8. Relationship with Retention and Log Compaction

### 8.1. Time- or Size-Based Retention

Kafka can delete old segments per `retention.ms` or `retention.bytes`. When records at the head of the log are deleted, the log start offset rises. A long-lagging consumer group may hold a committed offset lower than the log start offset.

Example:

~~~text
Before retention:
log start = 0
committed offset = 20
log end = 100

After retention:
log start = 50
committed offset = 20
log end = 150

Offset 20 is no longer in the log.
~~~

If the consumer returns after retention deleted offset 20, `earliest` moves it to 50, unable to recover records 20 through 49 from that topic. `latest` skips the remaining log to the end. `none` stops to require a manual decision.

Therefore, retention must exceed the longest duration a consumer can be down or lagging if business requirements demand reading all data.

### 8.2. Log Compaction

For topics with `cleanup.policy=compact`, Kafka retains the latest value per key in the compacted log and can remove older records. Offsets still increase per append history; the earliest available offset is not necessarily 0 and offsets may be non-contiguous.

`earliest` on a compacted topic means starting from the earliest surviving offset, not recovering every historical version of every key. If full event history replay is required, a compacted topic may not satisfy that requirement.

### 8.3. Consumer Group Offset Retention

In addition to topic record retention, brokers also enforce a retention policy on group committed offsets. If a group stays inactive for a long time and its offsets expire per broker settings such as `offsets.retention.minutes`, the next startup may find no committed offsets left.

At that point, `auto.offset.reset` can take effect even though the group ID has not changed. This is especially important for scheduled consumers, batch jobs, or services that may remain stopped for weeks.

Distinguish between:

- Topic retention determines which records still exist for consumers to read.
- Offset retention determines whether the broker still remembers the group's committed progress.

Both can affect the read position when a consumer comes back online.

## 9. Critical Operational Scenarios

| Scenario | Impact of auto.offset.reset | What to Watch |
|---|---|---|
| New group | Picks initial position for partitions | `earliest` replays retained history; `latest` skips history |
| Group ID change | New group lacks old offsets | Verify whether the change is intentional |
| Adding partitions | Group lacks offsets for new partitions | Reset policy applies to newly added partitions |
| Consumer lag exceeds retention | Committed offset may fall behind log start | `earliest` reads only from surviving data |
| Group offsets expire | Group may lose committed offsets | Reset policy is invoked again |
| Partition truncation | Offset may exceed log end | Investigate replicas and log state |
| Using `none` | Consumer errors when offsets are missing | Needs a clear offset initialization procedure |

### 9.1. Adding Partitions to a Topic

Suppose topic `orders` initially has 3 partitions and the consumer group has committed offsets for all three. Later the topic is expanded to 5 partitions. The two new partitions have no committed offsets for the group yet.

With `earliest`, the consumer can read existing records on the two new partitions from log start. With `latest`, the consumer starts at the log end of the two new partitions. With `none`, missing offsets can cause the consumer to throw an exception.

This is why changing partition counts requires a coordinated consumer plan. If new data is written to the new partitions immediately after expansion, the reset policy decides whether the group reads records written before it begins consuming those partitions.

### 9.2. Changing Group ID During Deployment

Changing a group ID usually creates an entirely new read progress track. If a group name is accidentally changed in environment config, the application may:

- Re-read many events if reset is `earliest`.
- Skip historical data if reset is `latest`.
- Fail to start if reset is `none`.

When changing a group ID, clarify whether the intent is to create an independent consumer or continue the old group's progress. To continue, keep the group ID or migrate offsets explicitly using a proper administrative procedure.

## 10. Active Offset Resets vs. auto.offset.reset

If a group already has valid committed offsets and operators want to replay data, changing `auto.offset.reset` has no effect. You must execute an intentional offset reset operation on the group.

Kafka provides `kafka-consumer-groups.sh` to inspect and reset offsets. Example checking progress:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-service \
  --describe
~~~

Example previewing resetting the group to the start of topic `orders`:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-service \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --dry-run
~~~

After verifying the scope and confirming the change is intentional, execute with `--execute` instead of `--dry-run`:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-service \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --execute
~~~

Before resetting:

1. Verify the exact cluster, group ID, topic, and partitions.
2. Stop or ensure the group has no active processing consumers.
3. Run `--dry-run` to preview target offsets.
4. Estimate replay impact on databases and downstream systems.
5. Record current offsets so you can reconcile or revert.
6. Execute only after clearly defining the data range to re-read.

Kafka tools may require the group to be inactive to reset offsets. Exact flags depend on Kafka version; check the help output of your deployed binary. For automated workflows, AdminClient can alter consumer group offsets, while still requiring careful management of group state and partition scope.

Active offset reset is a progress administration operation. `auto.offset.reset` is solely a fallback policy when a consumer has no valid offset.

## 11. Data Risks from Choosing the Wrong Policy

### 11.1. Using latest for Consumers Needing History

A new group using `latest` starts at the log end. If the topic already holds orders not yet billed, the group can skip those events and receive only new ones. Downstream systems can silently miss data without record-processing errors, because the consumer chose a valid starting point per configuration.

For business flows requiring every event, `earliest` or a controlled offset-initialization process is usually more appropriate. Evaluate replay capacity and idempotency to avoid duplicate side effects.

### 11.2. Using earliest for Consumers Needing Only Fresh Data

A new telemetry consumer may only need events produced after deployment. If `earliest` is used, the consumer reads all retained data, potentially causing heavy load and high lag while historical data has no value for that use case.

In that case `latest` can fit, provided the business accepts skipping historical records prior to initialization.

### 11.3. Using none Without a Provisioning Process

`none` catches groups missing offsets, but if deployment workflows do not pre-initialize offsets, consumers can halt immediately upon partition assignment. This often surfaces when group IDs change, offsets expire, or partitions are added to a topic.

Choosing `none` requires pairing it with an offset provisioning/reset step and clear alerting on `NoOffsetForPartitionException`.

### 11.4. Replays Can Create Duplicates

When `earliest` is used for a new group or after offset loss, old records can be reprocessed. If a listener previously produced side effects in another system under an earlier group ID, creating a new group does not automatically prevent business duplicates.

Use stable event IDs, unique constraints, inbox tables, or idempotent upserts to guard side effects. Never rely on a group's offset as a global idempotency key, since offsets are only meaningful within a partition and group.

## 12. Monitoring and Diagnosing Read Positions

To determine why a consumer started at a specific position, track the following details:

| Signal | Meaning |
|---|---|
| Group ID | Namespace storing progress |
| Topic and partition | Offset scope under inspection |
| Committed offset | Next position saved for the group |
| Log start offset | Earliest offset still retained by the broker |
| Log end offset | End of log, i.e., next position after the latest record |
| Consumer position | Position the consumer is currently reading in-session |
| Consumer lag | Distance between log end and consumer progress as computed by monitoring |

You can use describe to inspect group status:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-service \
  --describe
~~~

When investigating:

- If a valid committed offset exists, investigate why the consumer is not advancing; do not change the reset policy before finding the root cause.
- If the committed offset is lower than log start, check retention and how long the group was stopped.
- If no committed offset exists, check group ID, offset retention, new partitions, and reset policy.
- If the committed offset exceeds log end, check log truncation, leader elections, and cluster change history.
- If the group uses `none` and lacks offsets, check the provisioning workflow or reset operation.

Consumer lag is commonly calculated as log end offset minus committed offset. When offsets are reset, lag can jump suddenly. That may reflect intended policy behavior, so log and alert clearly to distinguish resets from a consumer suddenly losing progress.

Never inspect total lag alone. One partition may have lost offsets or stalled while other partitions operate normally. Always check per partition.

## 13. Testing auto.offset.reset

You can test reset policies on a dedicated test topic and separate group ID to avoid affecting running groups.

A basic test scenario:

1. Create a test topic with one partition.
2. Produce several records with recognizable keys/values.
3. Start a consumer with a new group ID and `earliest`.
4. Verify the consumer reads previously retained records.
5. Start another consumer with a new group ID and `latest`.
6. Verify the consumer skips existing history and receives records sent after startup.
7. Test `none` with a group ID lacking offsets and confirm the consumer reports missing-offset errors.
8. Inspect committed offsets via consumer group tools after processing.

To test retention expiry, configure short retention on the test topic, write records, commit offsets, and wait for the broker to delete eligible segments. Then restart the consumer and observe behavior when the committed offset is no longer in the log. Actual deletion timing depends on segment rolling and retention checks, so do not assume records vanish at the exact configured millisecond.

When testing a group that already has a valid offset, switch configuration from `latest` to `earliest` and restart. The consumer must resume from the existing committed offset; this is a key test proving the setting does not automatically reset a group on every restart.

## 14. Production Selection Principles

- Decide whether the consumer must read history or only new events before choosing a policy.
- Keep group IDs stable if you intend to continue committed progress.
- Use `earliest` when new groups must process retained history and downstream can handle replay load.
- Use `latest` when skipping history is acceptable to the business.
- Use `none` when offsets must be explicitly provisioned and failing fast on missing offsets is desired.
- Check both topic retention and committed-offset retention so a group returning after a long downtime does not lose progress.
- When adding partitions, evaluate how the reset policy applies to new partitions.
- Never change `auto.offset.reset` to rewind a group with valid offsets; use an audited offset-reset procedure with dry-run.
- Prepare listener idempotency if replays can repeat side effects.
- Monitor committed offsets, log start/end, consumer lag, and offset-out-of-range errors per partition.

`auto.offset.reset` is the policy governing how a consumer initializes or recovers its read position when a committed offset cannot be used. Choosing the right value keeps historical reading under control, prevents skipping critical events, and makes consumer startup behavior predictable.

# startOffset, Stored Offsets, and Policies When No Offset Exists

Kafka stores messages in topics by partition and tracks consumption progress using offsets. Each consumer group maintains its own progress on each partition. When a Spring Cloud Stream application starts up, the Kafka binder must decide where the consumer begins reading: resume from the committed offset, read from the beginning of retained data, or skip older data and only receive new messages.

Three frequently confused concepts are `startOffset`, committed offsets, and `resetOffsets`. `startOffset` selects the initial position when a group does not yet have a valid offset; the committed offset represents the group's stored progress; `resetOffsets` instructs the binder to ignore existing progress and reapply the start policy. Understanding this precedence order prevents unintended full-topic replays or accidentally skipping messages that need processing.

This lesson focuses on the Spring Cloud Stream Kafka message-channel binder, how to configure groups and offsets, behavior when offsets do not exist, expired offsets, replay strategies, and testing after resets.

## Learning Objectives

After this lesson, you will be able to:

- Explain an offset as the read position within each Kafka partition.
- Distinguish the committed offset from the consumer's current position.
- Understand `startOffset: earliest` and `startOffset: latest`.
- Explain the difference between consumers with an explicit group and anonymous groups.
- Configure `startOffset` and `resetOffsets` on the right Kafka binder binding.
- Recognize when the Kafka client's `auto.offset.reset` applies.
- Handle scenarios where offsets do not exist, have expired, or fall out of range of retained data.
- Choose a safe replay approach using a new group, controlled reset, or rebalance listener.
- Test first-time startup and restart behavior against a real Kafka broker.

## 1. What Is an Offset?

Kafka stores records inside each partition. Every record in a partition has a monotonically increasing offset number. An offset is the record's position within that partition, not a global sequence number across the topic.

For example, suppose topic `orders` has three partitions:

| Partition | Illustrative Offsets |
|---|---|
| orders-0 | 0, 1, 2, 3, 4, ... |
| orders-1 | 0, 1, 2, 3, ... |
| orders-2 | 0, 1, 2, 3, 4, 5, ... |

A consumer group might be reading partition 0 at position 4, partition 1 at position 2, and partition 2 at position 5. Therefore, no single offset represents the entire topic.

In Kafka, the committed offset is typically the next position the consumer needs to read. If a consumer processes the record at offset 12 and commits offset 13, the next startup will resume from record offset 13. This convention avoids confusion between the offset of the last processed record and the stored offset value.

### Current Position vs. Committed Offset

- **Current position:** the consumer's active position while running. The consumer may have polled and processed several records that have not yet been committed.
- **Committed offset:** the durably stored progress position for the consumer group. After a restart or rebalance, the consumer can resume from this position.
- **Log end offset:** the end position of data written to the partition; it indicates the current tail of the log, not where the consumer has processed up to.
- **Log start offset:** the earliest position still retained in the partition; data before this point may have been removed by retention or compaction.

~~~mermaid
flowchart LR
    A["Log start offset"] --> B["Committed offset"]
    B --> C["Current consumer position"]
    C --> D["Log end offset"]
    style B stroke-width:3px
~~~

The committed offset may lag behind the current position while the consumer is processing records that have not yet been committed. If the process stops before committing, some already-processed records may be redelivered. If committed too early before processing finishes, records may be skipped after a restart.

## 2. Committed Offsets Are Stored per Consumer Group

Kafka stores group progress internally within the cluster, typically via the internal `__consumer_offsets` topic. Each group has its own offset per topic partition. Two different groups can read the same topic independently and track different progress.

Example:

| Consumer Group | orders-0 | orders-1 |
|---|---:|---:|
| order-processor | 120 | 95 |
| order-audit | 80 | 140 |
| order-reporting | 150 | 150 |

If `order-processor` restarts, it resumes from its own group's committed offsets. The fact that `order-audit` has read up to a higher offset does not affect `order-processor`'s progress.

In Spring Cloud Stream, the group is declared on the binding:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
~~~

A binding with an explicit group creates a consumer group with a stable identity. If `group` is omitted, the binder creates an anonymous consumer group. Anonymous groups suit some independent consumption use cases, but should not be used when you need a stable group identity to track long-term progress or scale multiple instances sharing load.

### Why Does the Group Affect the Starting Position?

When a group has no committed offset yet, Kafka needs a policy to decide where to start reading. The Spring Cloud Stream Kafka binder provides `startOffset` and has different defaults for bindings with an explicit group versus anonymous bindings:

- Bindings with an explicit `group` default to starting from `earliest`.
- Anonymous bindings default to starting from `latest`.

This default can be overridden with `startOffset`. Once a group has a valid committed offset, the stored offset takes precedence and `startOffset` does not pull the consumer back to the beginning of the topic.

## 3. startOffset: earliest and latest

The Kafka binder supports two values for `startOffset`:

- `earliest`: start from the earliest readable offset in each assigned partition.
- `latest`: start from the current end of the partition and receive records written after that point.

Example configuration to read from the beginning of retained data:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              startOffset: earliest
~~~

Example configuration to receive only new messages when the group has no valid offset yet:

~~~yaml
spring:
  cloud:
    function:
      definition: monitorEvents
    stream:
      bindings:
        monitorEvents-in-0:
          destination: system-events
          group: live-monitor
      kafka:
        bindings:
          monitorEvents-in-0:
            consumer:
              startOffset: latest
~~~

### earliest Does Not Mean Offset 0 Always Exists

`earliest` is the earliest position still available in the log at the moment the consumer needs to start. If topic retention has already deleted older records, the consumer cannot read data that was purged. For compacted topics, Kafka may remove older records for the same key and retain only the latest values according to compaction policy. Thus, `earliest` is not synonymous with the entire history ever written.

### latest Can Skip Existing Data

If a new group is configured with `latest`, the consumer sets its starting position at the current tail of the log. Records that existed before that position was chosen will not be read by the new group. This is suitable for monitoring events emitted while the application runs, but unsuitable if the consumer must process all historical data.

## 4. Precedence Order: Committed Offset vs. startOffset

When the application starts, the Kafka binder determines the position based on the group and offset state:

1. If the group has a valid committed offset for the partition, the consumer resumes from the stored offset.
2. If the group has no offset for the partition, the binder applies the starting policy: `startOffset` or the corresponding default.
3. If the stored offset is no longer within the available log range, Kafka handles the out-of-range offset according to the consumer/binder reset policy.
4. If `resetOffsets: true`, the binder ignores existing committed offsets and applies `startOffset` to assigned partitions according to binder semantics.

Summary table:

| Group / Partition State | resetOffsets | Starting Position |
|---|---|---|
| Has valid committed offset | false | Resume from committed offset |
| No committed offset | false | Follow `startOffset` or default |
| Offset expired / missing | false | Follow reset policy when no valid offset exists |
| Has valid committed offset | true | Ignore old offset, apply `startOffset` |
| New group, never read before | true | Apply `startOffset` as on first run |

This is the most important takeaway: merely setting `startOffset: earliest` does not mean the consumer always reads from the beginning on every restart. If the group has a committed offset, the binder resumes from that offset unless a reset is requested.

## 5. Configuring resetOffsets

`resetOffsets` is a Kafka-binder-specific property. Its default is `false`. When set to `true`, the binder ignores existing committed offsets and applies the `startOffset` position, as if the binding had never consumed from the topic.

Example requesting to reread from the beginning every time the binding starts:

~~~yaml
spring:
  cloud:
    function:
      definition: rebuildOrderIndex
    stream:
      bindings:
        rebuildOrderIndex-in-0:
          destination: orders
          group: order-index-rebuild
      kafka:
        bindings:
          rebuildOrderIndex-in-0:
            consumer:
              startOffset: earliest
              resetOffsets: true
~~~

Example starting at the end of the log when the application starts:

~~~yaml
spring:
  cloud:
    function:
      definition: liveEventMonitor
    stream:
      bindings:
        liveEventMonitor-in-0:
          destination: system-events
          group: live-event-monitor
      kafka:
        bindings:
          liveEventMonitor-in-0:
            consumer:
              startOffset: latest
              resetOffsets: true
~~~

With `resetOffsets: true`, every time the binding starts, existing committed offsets are ignored. Consequently, `earliest` can cause the application to re-read large amounts of data and repeat side effects; `latest` can skip existing data. Only use it when you have a clear plan for replay, idempotency, and consumer group impact.

When a rebalance occurs after the initial partition assignment, the binder performs a seek according to the reset policy on newly assigned partitions that were not part of the initial assignment. This behavior must be accounted for when scaling instances or changing assignments.

### Do Not Combine resetOffsets with KafkaBindingRebalanceListener

If the application provides a `KafkaBindingRebalanceListener` bean to control offset seeking manually, do not set `resetOffsets: true`. Both mechanisms control the read position and the binder does not allow combining them. With a listener, keep `resetOffsets: false` and perform seeks within the listener logic.

## 6. Policy When No Offset Exists: auto.offset.reset

The Kafka client has a native `auto.offset.reset` property to decide behavior when no valid offset is found or the offset is out of range of the log. Common values:

| Kafka Client Value | Behavior |
|---|---|
| `earliest` | Read from the earliest available offset |
| `latest` | Read from the end of the log, waiting for new records |
| `none` | Throw an error if no valid offset is found |

The Spring Cloud Stream Kafka binder provides the binder-level property `startOffset` with two values: `earliest` and `latest`. The binder defaults to `earliest` for explicit groups and `latest` for anonymous groups. When configuring `startOffset`, use the binder property rather than guessing defaults from the Kafka client.

If fail-fast behavior corresponding to `auto.offset.reset=none` is required, inspect the native Kafka consumer configuration and how the binder sets `startOffset` in your version. Do not configure multiple reset properties simultaneously under the assumption they share the same precedence. Test new groups, expired offsets, and out-of-range offsets to confirm actual behavior.

Example native Kafka consumer configuration:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              configuration:
                auto.offset.reset: none
~~~

This snippet illustrates how to pass Kafka client properties through the binder. If `startOffset` is also configured, the value applied by the binder may dominate initialization behavior; avoid setting conflicting policies. For applications needing fail-fast behavior, verify the effective configuration after the binder creates the consumer and test on your exact version.

## 7. Anonymous Groups vs. Explicit Groups

When `group` is omitted, the Spring Cloud Stream Kafka binder creates an anonymous consumer group. The binder generates an internal group ID for the consumer to function; the application does not have a stable group name managed directly as with an explicit group.

Common characteristics:

- Anonymous groups default to `latest` when no offset exists.
- Independent applications can receive their own data instead of sharing load in a named group.
- Do not rely on anonymous groups to maintain long-term consumption progress across deployments.
- When partitions need to be shared across multiple instances, declare the same explicit group across instances of the same application.

Example of an explicit group:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        inventory-in-0:
          destination: orders
          group: inventory
~~~

Three replicas of the application using this binding and the same `inventory` group will join the same consumer group. Kafka distributes partitions among the members. Using a different group gives that consumer group independent progress and allows it to read the topic separately.

Do not confuse replica count with group count. Scaling instances within the same group does not create an independent processing copy of the entire topic; instances share the partitions. If another application needs to read all events independently, that application needs its own group.

## 8. Offsets Can Expire or Become Invalid

Committed offsets do not necessarily persist forever. Kafka brokers enforce an offset retention policy for consumer groups. On modern Kafka brokers with common default settings, offsets for a group with no active members may expire after roughly seven days; the exact duration depends on `offsets.retention.minutes` and broker configuration.

Beyond expiration, a committed offset may fall outside the log range due to topic retention or administrative operations. In that case, the consumer needs a reset policy to pick a new position.

Situations to watch for:

- A consumer group has had no active members for a long period.
- Topic retention deletes older records.
- A topic is deleted and recreated with the same name.
- Partitions are modified or data is regenerated.
- The consumer's stored offset is older than the current log start offset.

When no valid committed offset remains, `startOffset` or `auto.offset.reset` becomes relevant again. Inspect consumer and broker logs to distinguish a brand-new group from an expired or out-of-range offset.

## 9. Configuration Examples for Three Startup Policies

### Business Group Needing Historical Processing

Use an explicit group and `earliest` so the first run reads from retained data:

~~~yaml
spring:
  cloud:
    function:
      definition: orderProjection
    stream:
      bindings:
        orderProjection-in-0:
          destination: orders
          group: order-projection
      kafka:
        bindings:
          orderProjection-in-0:
            consumer:
              startOffset: earliest
              resetOffsets: false
~~~

After the initial processing, Kafka stores the committed offset. When the application restarts, it resumes from the committed offset rather than going back to the beginning of the topic.

### Consumer Interested Only in New Data

Use `latest` for a new group:

~~~yaml
spring:
  cloud:
    function:
      definition: liveDashboard
    stream:
      bindings:
        liveDashboard-in-0:
          destination: system-events
          group: live-dashboard
      kafka:
        bindings:
          liveDashboard-in-0:
            consumer:
              startOffset: latest
              resetOffsets: false
~~~

The new group starts at the end of the log. Once committed offsets exist, restarts resume from the stored offsets.

### Intentionally Re-reading from the Beginning

Use `resetOffsets: true` with `earliest` when prepared for a replay:

~~~yaml
spring:
  cloud:
    function:
      definition: rebuildOrderProjection
    stream:
      bindings:
        rebuildOrderProjection-in-0:
          destination: orders
          group: order-projection-rebuild
      kafka:
        bindings:
          rebuildOrderProjection-in-0:
            consumer:
              startOffset: earliest
              resetOffsets: true
~~~

Use a separate group when rebuilding a projection so you do not alter the progress of the running production consumer. Once the projection is rebuilt, you can switch traffic or apply the appropriate synchronization strategy.

## 10. Seeking to an Arbitrary Offset

`startOffset` only chooses `earliest` or `latest`; it cannot select a specific offset number such as 1200. If you need to start from an arbitrary offset or a timestamp, the Kafka binder supports `KafkaBindingRebalanceListener` so the application can execute a seek when partitions are assigned.

The listener is invoked during assignment/rebalance and has access to the consumer and the list of assigned partitions. The application can call the appropriate seek API for each partition once the desired position is determined.

Configuration guidelines:

- Provide a bean implementing `KafkaBindingRebalanceListener`.
- Set `resetOffsets: false`.
- Seek only on appropriate partitions, typically on initial assignment or newly assigned partitions.
- Define clear behavior when a partition is reassigned after a rebalance.
- Never seek forward arbitrarily without verifying prior messages were processed.
- Log the partition, offset before, and offset after seeking for auditability.

Do not perform manual seeks alongside `resetOffsets: true`. If a specific range needs to be replayed, consider testing with a separate consumer group first to avoid altering the production group's progress.

## 11. Distinguishing Kafka Message-Channel Binder from Kafka Streams Binder

Spring Cloud Stream offers two common ways to integrate with Kafka: the message-channel binder and the Kafka Streams binder. Do not mechanically apply the same offset policy to both.

With the Kafka message-channel binder:

- Consumer bindings use `startOffset` and `resetOffsets`.
- Explicit groups default to `earliest`; anonymous groups default to `latest`.
- `resetOffsets: true` can bypass committed offsets according to binder semantics.
- `KafkaBindingRebalanceListener` can control arbitrary seeks.

With the Kafka Streams binder:

- `startOffset` is configured per Kafka Streams binding.
- The default is typically `earliest` for a new consumer.
- `latest` can be set per binding if the application only needs new data.
- The message-channel binder's `resetOffsets` has no effect on the Kafka Streams binder.

Example `startOffset` configuration for a Kafka Streams binding:

~~~yaml
spring:
  cloud:
    function:
      definition: analyzeOrders
    stream:
      kafka:
        streams:
          bindings:
            analyzeOrders-in-0:
              consumer:
                startOffset: latest
~~~

Kafka Streams also has state stores, changelogs, and its own processing guarantees. If you reset input offsets while keeping old state stores, the resulting state may no longer match the replayed data. When rebuilding state, plan for both input offsets and state stores rather than only changing `startOffset`.

## 12. Inspecting Offsets and Consumer Progress

To understand where a consumer stands, inspect the committed offset, log end offset, and consumer lag together. Lag is generally calculated as log end offset minus committed offset per partition, though exact display depends on the tool.

Useful Kafka CLI commands:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-processor
~~~

This command displays partition assignments, current offsets, log end offsets, and lag for the group.

To list groups:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list
~~~

To check how many partitions a topic has:

~~~bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders
~~~

Avoid running offset-reset commands directly on a production group while consumers are active without a coordinated plan. Before making changes, record current offsets, stop or coordinate consumers, define the partition scope, and prepare a recovery plan.

## 13. Replay with a New Group vs. Resetting the Existing Group

These two approaches have different impacts:

| Replay Approach | Pros | Risks / Considerations |
|---|---|---|
| Create a new group with `earliest` | Does not alter the production group's offsets | Consumes extra resources; side effects still require idempotency |
| Reset the existing group to `earliest` | Reprocesses using the same group | Production consumer may re-read massive amounts of data |
| Use `resetOffsets=true` | Binder applies `startOffset` instead of committed offsets | May unexpectedly replay or skip messages on every restart |
| Use a rebalance listener to seek a specific offset | Fine-grained control over starting position | Must handle assignments/rebalances carefully |

If the goal is to rebuild a projection, a new group is usually easier to isolate. If the goal is to recover the production group itself, stop consumers or coordinate offset changes carefully, verify idempotency, and monitor lag after resuming.

Replay is not just a technical offset decision. It can resend emails, recreate transactions, or update data again. Consumers must be idempotent and have safeguards for side effects.

## 14. Testing startOffset and Committed Offsets

A test suite should cover multiple restarts with the same group:

### Testing Initial Startup with an Explicit Group

1. Create a topic with pre-existing records.
2. Configure an explicit group and `startOffset: earliest`.
3. Start the consumer.
4. Verify the consumer reads from the earliest retained offset.
5. Wait for successful processing and verify committed offsets are recorded.

### Testing Restart with Committed Offsets

1. Stop the consumer after part of the data has been processed and committed.
2. Produce additional new records.
3. Restart with the same group.
4. Verify the consumer resumes from the committed offset.
5. Verify `startOffset: earliest` does not return the consumer to the beginning of the topic when stored offsets are still valid.

### Testing resetOffsets

1. Establish committed offsets in the middle of the topic.
2. Configure `startOffset: earliest` and `resetOffsets: true`.
3. Start the binding according to the test plan.
4. Verify the binder ignores old offsets and seeks to the beginning of retained data.
5. Verify the consumer can re-read already-processed records; verify idempotency.

### Testing Invalid or Expired Offsets

- Leave the group inactive long enough according to configured offset retention, or simulate a new group.
- Lower topic retention in the test environment so old offsets fall outside the log.
- Verify the consumer applies the expected reset policy.
- Record logs and newly committed offsets.

Do not wait seven days in automated tests. Use a test broker with short retention settings or create a new group to exercise the missing-offset path.

## 15. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Consumer does not read older messages | New group using `latest` or an anonymous group | Declare an explicit group and `startOffset: earliest` |
| Changed `startOffset`, yet consumer continues from old offset | Group already has valid committed offsets | Use a new group or controlled `resetOffsets` |
| Consumer re-reads entire topic after restart | `resetOffsets: true` or a new group | Check reset policy and group ID |
| Consumer skips existing records | New group using `latest` | Use `earliest` if history is needed |
| Consumer starts from an unexpected offset | Topic retention or out-of-range offset | Check log start offset and reset policy |
| Anonymous consumer does not preserve progress as expected | Binder-generated group ID is not stable for operational tracking | Use an explicit group |
| Replay causes duplicate side effects | Consumer is not idempotent | Use event IDs, inbox, or idempotency keys |
| `resetOffsets` has no effect with Kafka Streams | Using the Kafka Streams binder | Configure `startOffset` on the Kafka Streams binding |
| Arbitrary seek conflicts with reset | Listener configured together with `resetOffsets=true` | Set `resetOffsets=false` and manage seeks in the listener |
| Consumer lag spikes after changing offset | Consumer is re-reading a large backlog | Monitor throughput, scale carefully, and assess replay impact |

When diagnosing, inspect in order: group ID, per-partition committed offsets, `startOffset`, `resetOffsets`, log start/end offsets, and the binder in use. Never infer the read position solely from YAML without checking actual offsets on the broker.

## 16. Hands-on Exercise: Building a Consumer with an Explicit Offset Policy

Build a `processOrder` consumer reading the `orders` topic:

1. Declare the `processOrder` function accepting order events.
2. Configure destination `orders` and group `order-processor`.
3. Set `startOffset: earliest` for the initial startup.
4. Send several messages before starting the consumer.
5. Start the consumer and verify it reads existing data.
6. Stop the consumer after some records are committed.
7. Send more messages and restart with the same group.
8. Verify the consumer resumes from the committed offset without returning to the start of the topic.
9. Create a new group `order-rebuild` configured with `earliest`; verify the new group reads history independently.
10. Try `latest` with a new group and verify old records are skipped.
11. In a test environment, enable `resetOffsets: true` and verify existing offsets are ignored.
12. Run `kafka-consumer-groups --describe` to compare current offset, log end offset, and lag.
13. Check for duplicate side effects during replay and verify consumer idempotency.

Acceptance checklist:

| Item | Verification Outcome |
|---|---|
| Group identity | Stable explicit group |
| Initial position | `earliest`/`latest` matches requirements |
| Stored offset | Restart resumes from committed offset |
| `resetOffsets` | Enabled only with a reset/replay plan |
| Offset retention | Behavior when offsets expire is understood |
| Out-of-range | Policy defined when offsets fall outside the log |
| Replay | Replay scope and group are controlled |
| Idempotency | Reprocessing does not duplicate side effects |
| Observability | Offsets and lag can be inspected per partition |
| Binder type | Message-channel and Kafka Streams binders distinguished |

## Conclusion

`startOffset` determines the starting position when a consumer group does not yet have a valid committed offset; the group's stored offset takes precedence as long as it remains valid. With the Kafka message-channel binder, explicit groups default to `earliest` and anonymous groups default to `latest`. `resetOffsets: true` instructs the binder to ignore committed offsets and reapply `startOffset`, which can cause replays or skipped data.

Declare stable groups for business consumers, choose `earliest`/`latest` based on requirements, only reset when idempotency and an operational plan are ready, and inspect actual offsets and lag per partition. When seeking to arbitrary offsets, use `KafkaBindingRebalanceListener` with `resetOffsets` disabled. Distinguish the message-channel binder from the Kafka Streams binder to avoid applying the wrong configuration.

## References

- [Spring Cloud Stream Kafka Binder – Resetting Offsets](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka_overview.html)
- [Spring Cloud Stream Kafka Binder – Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/configuration-options.html)
- [Apache Kafka – Consumer Configs: auto.offset.reset](https://kafka.apache.org/documentation/#consumerconfigs_auto.offset.reset)
- [Apache Kafka – Consumer Groups](https://kafka.apache.org/documentation/#intro_consumers)

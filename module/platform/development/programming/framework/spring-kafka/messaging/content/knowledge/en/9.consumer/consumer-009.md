# Which Offset Does a Consumer Restart From

## Learning objectives

In the **Consumer** chapter, this lesson explains which read position Kafka chooses when a consumer starts for the first time, restarts after a failure, or rejoins a consumer group. The focus is on committed offset, consumer position, and the `auto.offset.reset` property.

**SPRING_KAFKA_MESSAGING** focuses on building applications that send and receive Kafka events using Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, while helping learners understand topics, partitions, offsets, consumer groups, serialization, retries, dead-lettering, transactions, exactly-once, concurrency, and testing. Understanding offsets properly helps a consumer recover after a restart without accidentally skipping data or re-reading too many records.

After this lesson, learners will be able to:

- Distinguish a committed offset from a consumer's current read position.
- Explain how Kafka restores progress per consumer group.
- Configure `auto.offset.reset` with `earliest`, `latest`, or `none`.
- Understand why `auto.offset.reset` does not overwrite committed offsets on every application restart.
- Identify the impact of `group.id`, retention, new partitions, and rebalances.
- Configure appropriate acknowledgment/commit settings in Spring Kafka.
- Intentionally seek or reset offsets when data replay is needed.

## 1. Where does a consumer resume reading from?

Kafka stores records by topic and partition. Each record within a partition has a definite offset. A consumer reads records in offset order within its assigned partitions.

When a consumer processes a record, two concepts must be distinguished:

- **Consumer position:** the next position the consumer will read in the current session.
- **Committed offset:** the position durably stored by the consumer group so it can resume after a consumer stops, restarts, or a partition is handed to another consumer.

Committed offsets are stored per consumer group and topic-partition pair. It is not a single global offset for the entire topic.

For example, a consumer reading partition 0:

~~~text
Offset:             40   41   42   43   44   45
                    |    |    |    |    |    |
Consumer processed: ✓    ✓
Committed offset:        42
Next read position:           42
~~~

If the consumer processed record offset 41 and committed offset 42, the value 42 represents the next position to read. When the consumer restarts in the same group, Kafka can resume from offset 42.

Therefore, when asking "which offset does the consumer restart from", you must check the latest committed offset for each partition. You cannot look only at a single offset value for the whole topic.

## 2. Kafka stores progress per consumer group

Each consumer group has an identifier `group.id`. Kafka manages reading progress separately for each group and each partition.

Example topic `commerce.order.created` with 3 partitions and two consumer groups:

~~~text
Topic: commerce.order.created

Group: billing-service
  partition 0 -> committed offset 120
  partition 1 -> committed offset 95
  partition 2 -> committed offset 210

Group: analytics-service
  partition 0 -> committed offset 80
  partition 1 -> committed offset 95
  partition 2 -> committed offset 175
~~~

Two groups can read the same topic while keeping independent progress. When a `billing-service` consumer restarts, it resumes from `billing-service`'s committed offsets; it does not use `analytics-service`'s offsets.

Kafka stores consumer offsets in the internal `__consumer_offsets` topic. Applications do not need to write their own offset files or store offsets in in-memory variables for normal progress recovery.

### 2.1. Keeping the same group.id on restart

If the application restarts with the same `group.id` and the partitions still belong to that group, Kafka uses the valid committed offset saved for each partition.

For example:

- Before stopping, `billing-service` committed offset 500 for partition 0.
- The application is redeployed with the same `group.id`, `billing-service`.
- The consumer joins the group and receives partition 0.
- The consumer resumes reading from position 500.

The `auto.offset.reset` property does not overwrite offset 500 merely because the application just restarted.

### 2.2. Changing group.id creates independent reading progress

If you change `group.id` from `billing-service` to `billing-service-v2`, Kafka treats it as a different consumer group. The new group has no committed offsets for those partitions yet, so the `auto.offset.reset` policy can apply.

This is why an application can re-read old data after changing `group.id` even though the topic and handler code did not change.

Do not change `group.id` on every deployment if the goal is to continue the existing group's progress. If an independent reading stream is needed, creating a new group is an intentional action.

## 3. What does auto.offset.reset decide?

`auto.offset.reset` is a Kafka consumer setting. It determines the starting position when the consumer group has no valid committed offset for a partition or the committed offset no longer falls within the offset range the broker can serve.

Three common options:

| Value | Behavior | Use case |
|---|---|---|
| `earliest` | Reads from the earliest offset still retained in the partition | Want to process data still within retention |
| `latest` | Starts from the end of the partition and waits for new records | Only care about data produced after the group starts |
| `none` | Raises an error if no valid offset exists | Want the application to stop so operators explicitly decide the position |

### 3.1. earliest

With `earliest`, when the group has no valid offset, the consumer starts from the smallest offset currently retained by the broker.

For example, a partition has existing offsets from 100 to 150:

~~~text
Retained offsets: 100 ... 150
Group has no committed offset
auto.offset.reset=earliest

Starting position: 100
~~~

`earliest` does not always mean reading from offset 0. If retention has deleted older segments and the current log start offset is 100, the consumer can only start at 100.

This option fits new consumers that need to process retained historical data, analytics consumers, or test environments that want to read an existing topic.

### 3.2. latest

With `latest`, when the group has no valid offset, the consumer starts at the end of the partition at the moment the initial position is established and waits for new records.

Example:

~~~text
Existing offsets: 100 ... 150
Group has no committed offset
auto.offset.reset=latest

Initial position: end of partition
Subsequent new records: read continuously
~~~

The consumer does not re-read existing historical records in the partition when `latest` applies to a new group. This option fits streams that only need to process events occurring from the time the consumer starts watching.

Be careful when deploying a new consumer with `latest`: if the application needs historical data to build initial state, records prior to the start time will be skipped for that group.

### 3.3. none

With `none`, the consumer does not automatically pick `earliest` or `latest` when a valid offset is missing. Kafka raises an error, typically `NoOffsetForPartitionException`, so the application or operator handles it explicitly.

This option fits when automatically picking a starting point could have business consequences, such as financial processing or migrations requiring strict offset control.

`none` does not mean Kafka recovers offsets on its own. The application must provide a valid offset or an operator must reset the group before the consumer proceeds.

### 3.4. Distinguishing starting position from retained data range

`earliest` only reads from the earliest still-existing offset. It does not restore data already deleted by retention, compaction, or administrative actions.

`latest` also does not delete old records. It only determines the initial read position for partitions lacking a valid offset.

`auto.offset.reset` is a read-position selection policy, not a data deletion policy or a topic retention change.

## 4. When is auto.offset.reset applied?

This setting is typically triggered in the following cases:

1. A new consumer group has never committed an offset for the partition.
2. An existing group is assigned a newly added partition that has no committed offset yet.
3. The committed offset is no longer valid because the log start offset advanced due to retention or partition data changed.
4. The consumer requests an offset outside the range the broker can serve.

If the group already has a valid committed offset, the consumer resumes from that offset. This is the single most important rule when analyzing restart behavior.

### 4.1. Example with a new group

A topic has partition 0 containing offsets 0 through 999. Group `billing-v1` has never read the topic.

- `earliest`: starts from the earliest retained offset, which is 0 in this example.
- `latest`: starts at the end of the partition, after existing records.
- `none`: fails with an error because the group has no valid offset.

### 4.2. Example with a group that already has an offset

Group `billing-service` has committed offset 700, and the partition still retains offsets 0 through 999.

Whether `auto.offset.reset` is configured as `earliest` or `latest`, the consumer still resumes from 700. The reset policy is not used because the committed offset is still valid.

### 4.3. Example when the offset was removed by retention

The group committed offset 100, but retention deleted older segments and the partition's log start offset is now 300.

Committed offset 100 falls outside the readable range. When the consumer detects the offset is no longer valid, `auto.offset.reset` applies:

- `earliest`: moves to offset 300, the earliest retained offset.
- `latest`: moves to the end of the partition.
- `none`: stops with an error requiring intervention.

If `earliest` is used in this case, the consumer has still lost the ability to read records 100 through 299 because the broker no longer retains them. Monitor retention and consumer lag to avoid losing the replayable data window.

## 5. Configuration in Spring Boot and Spring Kafka

Group ID and `auto.offset.reset` can be configured in `application.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: billing-service
      auto-offset-reset: earliest
      enable-auto-commit: false
~~~

Meaning:

- `bootstrap-servers`: broker addresses the consumer connects to.
- `group-id`: consumer group name used to store reading progress.
- `auto-offset-reset`: policy when the group has no valid offset.
- `enable-auto-commit: false`: lets the Spring Kafka listener container manage commits according to the acknowledgment mode.

In Spring Kafka, the listener container typically manages offsets instead of the Kafka consumer's auto-commit when `enable.auto.commit` is not explicitly enabled. Setting `false` explicitly makes the configuration's intent clear and prevents timer-based commits independent of listener execution.

You can configure directly on `@KafkaListener`:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service"
)
public void handle(OrderCreated event) {
    // Process order event.
}
~~~

`groupId` on the annotation specifies the group for the listener and overrides the default group ID from the consumer factory for that endpoint. Keep the group ID stable across deployments if you want to continue existing progress.

### 5.1. Does changing auto.offset.reset make the consumer re-read from the beginning?

No, if the group still has a valid committed offset.

For example, previously configured:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: billing-service
      auto-offset-reset: latest
~~~

The group committed offset 500. Then you change it to:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: billing-service
      auto-offset-reset: earliest
~~~

The consumer still resumes from offset 500. To re-read from the beginning, you must reset the committed offset or use a new group ID with no prior progress while choosing `earliest`.

### 5.2. Group ID varying by environment

If the group ID is built from application name plus environment, keep the convention stable:

~~~text
billing-service-dev
billing-service-staging
billing-service-prod
~~~

Each group has its own progress. Do not use a different group ID on every local run if you want to continue offsets from the previous run. Conversely, sharing the same group ID across multiple instances of the same application is the standard way for instances to share partitions.

## 6. Offset commit and acknowledgment in Spring Kafka

Which offset a consumer restarts from depends directly on when the offset was committed.

A Kafka consumer may have read a record and advanced its in-memory consumer position, yet that does not mean the group has saved new progress. If the application stops before committing, the record may be redelivered after a restart or rebalance.

### 6.1. AckMode in Spring Kafka

Spring Kafka provides acknowledgment modes for the listener container:

| AckMode | High-level behavior |
|---|---|
| `RECORD` | Commits after the listener finishes processing each record |
| `BATCH` | Commits after all records from a poll have been processed |
| `TIME` | Commits when the configured time interval elapses and corresponding records are processed |
| `COUNT` | Commits when the configured record count is reached |
| `COUNT_TIME` | Combines time and record count conditions |
| `MANUAL` | Listener explicitly calls acknowledge; container commits per mode semantics |
| `MANUAL_IMMEDIATE` | Requests an immediate commit when acknowledge is called on the consumer thread |

`BATCH` is the common default for listener containers. Check the actual container/factory configuration if the application customizes acknowledgment.

### 6.2. RECORD example

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        orderListenerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.RECORD);

    return factory;
}
~~~

With `RECORD`, after the listener successfully processes one record, the container can commit the corresponding offset per configuration. If the listener throws an exception, committing depends on the error handler and error-handling policy.

### 6.3. MANUAL example

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service",
    containerFactory = "manualAckListenerFactory"
)
public void handle(
        OrderCreated event,
        Acknowledgment acknowledgment) {

    billingService.process(event);

    acknowledgment.acknowledge();
}
~~~

The factory must be configured with `AckMode.MANUAL` or `MANUAL_IMMEDIATE` accordingly. Only acknowledge after required business work is complete.

If you acknowledge before a database write succeeds, the consumer may commit the offset and then stop; on restart, Kafka will not redeliver that record even though business work never finished. If processing finishes without committing, the record may be redelivered and requires idempotency.

### 6.4. Offset commit is not a database commit

A Kafka offset commit and a database transaction are two separate operations. If a listener updates the database and then commits the offset, a failure between the two can cause the record to be redelivered. If it commits the offset before updating the database, a failure can lose the chance to reprocess.

Therefore, listeners should be designed to be idempotent or use an appropriate integration pattern such as Inbox/Outbox when coordinating Kafka with a database.

## 7. What happens when a consumer restarts?

Suppose a listener processes partition 0 in order:

~~~text
Processed:   offset 40, 41
Committed:   offset 42
Unprocessed: offset 42, 43, 44
~~~

When the process stops:

1. The consumer leaves the group or is detected as no longer active.
2. Kafka may rebalance and assign the partition to another consumer.
3. When the new consumer receives the partition, it retrieves the group's committed offset.
4. The consumer resumes from offset 42 if that offset is still valid.
5. If there is no valid offset, `auto.offset.reset` applies.

~~~mermaid
sequenceDiagram
    participant A as Consumer instance
    participant K as Kafka group coordinator
    participant O as __consumer_offsets
    participant B as Broker partition

    A->>B: Poll records
    B-->>A: Offset 40, 41
    A->>A: Process record
    A->>K: Commit offset 42
    K->>O: Save committed offset
    Note over A: Process restart
    A->>K: Join consumer group
    K->>O: Read saved offset
    O-->>K: Offset 42
    K-->>A: Assign partition and offset 42
    A->>B: Poll from offset 42
    B-->>A: Next record
~~~

The committed offset represents the next position to read. If the broker has offset gaps due to compaction or control records, the actual next record may have an offset higher than the committed value.

## 8. Rebalances and new partitions

A rebalance occurs when consumer group membership changes or subscriptions/assignments change. A partition may be handed to another consumer, yet progress still belongs to the group rather than the individual instance.

When a new consumer receives a partition:

- If the group has a valid committed offset, the consumer uses that offset.
- If the group has no offset for the partition yet, `auto.offset.reset` decides the position.
- If the committed offset is outside the retained range, the reset policy applies.

A common scenario is increasing a topic's partition count. The new partitions have no committed offset for the existing group yet. The consumer assigned a new partition uses `auto.offset.reset` to pick its starting position.

Changing concurrency or instance count does not automatically reset offsets for existing partitions. Kafka redistributes partitions, while progress remains managed by group and partition.

## 9. Explicitly moving a consumer to a desired offset

There are situations requiring data replay, such as fixing a processing bug, re-running reports, or migrating consumers. In those cases, you can use one of the following approaches:

- Create a new consumer group to read independently.
- Use the `kafka-consumer-groups` tool to reset the existing group's offsets.
- Use the seek API in the application to change the consumer's read position.

Distinguish between a durable group offset reset and a seek within a running consumer session.

### 9.1. Resetting with kafka-consumer-groups

First, inspect current progress:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-service \
  --describe
~~~

Preview the plan to reset the topic to earliest:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-service \
  --topic commerce.order.created \
  --reset-offsets \
  --to-earliest \
  --dry-run
~~~

After confirming the right group, topic, and reset scope, run:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-service \
  --topic commerce.order.created \
  --reset-offsets \
  --to-earliest \
  --execute
~~~

Commonly used reset options:

| Option | Meaning |
|---|---|
| `--to-earliest` | Sets to the earliest retained offset |
| `--to-latest` | Sets to the end of the partition |
| `--to-offset N` | Sets to a specific offset |
| `--shift-by N` | Shifts the offset relatively |
| `--to-datetime` | Selects position by timestamp |
| `--by-duration` | Selects position by duration if supported by the Kafka version |

Normally the consumer group must be inactive when resetting offsets with this tool. Stop all consumers in the group before executing; if the group is still active, the reset command may be rejected or the new progress may be overwritten by consumers.

Always run `--dry-run` first, record the current state, and only run `--execute` after verification. After resetting, start the consumer so it reads from the new offsets.

On Windows, use the corresponding script in the `bin\windows` directory, such as `kafka-consumer-groups.bat`.

### 9.2. Using a new group ID for independent replay

If you want to run a replay stream without altering the progress of a group serving production, you can use a different group ID:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-replay-2026"
)
public void replay(OrderCreated event) {
    // Process or reconcile data according to the replay plan.
}
~~~

Combined with `auto.offset.reset=earliest`, the new group will start from the earliest retained offset.

This approach creates independent progress, but it can still cause business side effects if the listener writes data or calls external services. Use a dedicated replay consumer, dry-run mode, or idempotent logic before running reprocessing.

### 9.3. Seeking in Spring Kafka

Spring Kafka provides `ConsumerSeekAware` and `ConsumerSeekCallback` so listeners can control read positions when partitions are assigned or on application demand.

Illustrative example seeking partition 0 to offset 100 when the partition is assigned:

~~~java
@Component
public class OrderReplayListener implements ConsumerSeekAware {

    @Override
    public void registerSeekCallback(ConsumerSeekCallback callback) {
        // Spring registers the callback to control the read position.
    }

    @Override
    public void onPartitionsAssigned(
            Map<TopicPartition, Long> assignments,
            ConsumerSeekCallback callback) {

        TopicPartition partition =
            new TopicPartition("commerce.order.created", 0);

        if (assignments.containsKey(partition)) {
            callback.seek(
                partition.topic(),
                partition.partition(),
                100L
            );
        }
    }
}
~~~

This is an illustrative example of an intentional seek. If you unconditionally seek to offset 100 every time the partition is assigned, the application will re-read from that position after every rebalance. In production, enforce clear conditions to avoid unintended repetition.

Seeking changes the read position of the current consumer. To manage long-term progress across restarts, understand how offsets are committed after seeking and processing records. If offsets are committed after replay, the group's committed offset will change as processing proceeds.

## 10. Comparing restart behaviors

| Scenario | Starting position |
|---|---|
| Restart with same `group.id`, offset still valid | Stored committed offset |
| Restart with same `group.id`, offset uncommitted after processing | Uncommitted records may be re-read |
| New group ID with `earliest` | Earliest retained offset |
| New group ID with `latest` | End of partition, waiting for new records |
| New group ID with `none` | Error because no valid offset exists |
| New partition added to topic | Applies `auto.offset.reset` for the partition without an offset |
| Committed offset removed by retention | Applies `auto.offset.reset` |
| Group reset via admin tool | Starts from the reset offset once the consumer rejoins |
| Seek in listener container | Uses sought position in the consumer session, then commits per configuration |

## 11. Common errors on consumer restart

| Symptom | Possible cause | How to check |
|---|---|---|
| Consumer re-reads from the beginning after deploy | `group.id` changed or group had no valid offset | Check `group.id` and `kafka-consumer-groups --describe` |
| Consumer skips old data | New group uses `latest` | Check `auto.offset.reset` and startup timing |
| Switched to `earliest` but still continues from old offset | Group still has a valid committed offset | Check committed offset per partition |
| Consumer reports `NoOffsetForPartitionException` | Using `none` while group has no valid offset | Reset offsets or choose an appropriate policy |
| Consumer jumps back to start of retained data | Committed offset was removed by retention and policy is `earliest` | Check log start offset and consumer lag |
| Consumer processes duplicates after restart | Records were processed but offsets were not committed | Check ack mode and idempotency design |
| Consumer loses records after restart | Offsets committed before business work completed | Check processing order and acknowledgment |
| New partition reads from `latest` | Group has no offset for the new partition yet | Check partition expansion and reset policy |
| Offset reset has no effect | Consumer was still active or not restarted after reset | Stop group, dry-run, execute, and restart |

## 12. Testing restart and offset behavior

Test against real Kafka in an isolated environment using EmbeddedKafka or Testcontainers.

Scenarios to verify:

1. New group with `earliest` reads currently retained records.
2. New group with `latest` skips historical data and receives new records.
3. Group that committed an offset and restarted resumes from the committed offset.
4. Changing group ID creates independent reading progress.
5. Consumer processing a record and stopping before commit can receive the record again.
6. A newly added topic partition uses the reset policy when the group has no offset.
7. An expired/invalid old offset triggers the reset policy or `none` error.
8. Seek positions the consumer at the right partition and offset.
9. `AckMode` and error handlers produce the expected commit behavior when the listener succeeds or fails.

When writing restart tests, wait for the consumer group to complete assignment and wait for the offset commit to be recorded before stopping the consumer. Stopping immediately after the listener is invoked may cause the test to observe varying results depending on commit timing.

You can use `kafka-consumer-groups --describe` to confirm committed offsets and lag in the test environment. Do not rely solely on a "listener received record" log to conclude that the offset was committed.

## 13. Offset selection checklist for deployment

- [ ] Is `group.id` stable across restarts and deployments?
- [ ] Does the consumer group have committed offsets per partition?
- [ ] Is `auto.offset.reset` explicitly chosen as `earliest`, `latest`, or `none`?
- [ ] Is it understood that `earliest` only starts from retained data?
- [ ] Has the risk of skipping historical data when using `latest` been evaluated?
- [ ] Are `enable.auto.commit` and Spring Kafka `AckMode` clearly configured?
- [ ] Are offsets committed only after processing satisfies business conditions?
- [ ] Can the listener tolerate redelivered records?
- [ ] Is consumer lag monitored to prevent offsets from being evicted by retention?
- [ ] Is there a dry-run and approval process before resetting production offsets?
- [ ] Is there a separate group or idempotent mechanism for replay?
- [ ] Have tests verified restart, rebalance, and new partition behavior?

## Conclusion

When a consumer restarts, Kafka prioritizes the valid committed offset stored for each partition of the consumer group. `auto.offset.reset` is only applied when the group has no valid offset or the offset has fallen outside the range retained by the broker. `earliest` reads from the beginning of retained data, `latest` starts at the end of the partition, and `none` requires the application or operator to supply an explicit position.

In Spring Kafka, this behavior is tightly coupled to `group.id`, acknowledgment mode, and when the listener container commits offsets. For controlled replay, you can reset offsets using Kafka tools, create a new group, or use seek. Combining offset policies with idempotency, consumer lag monitoring, and restart tests helps consumer flows recover accurately and minimizes lost or duplicated events.

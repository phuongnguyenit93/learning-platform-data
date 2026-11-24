# Consumer Group and Committed Offset

In Kafka, a consumer group allows multiple consumers to share the work of reading data from a set of topics. Kafka tracks each group's progress via a **committed offset** per partition. Together, these two mechanisms enable horizontal processing scalability, resuming work after a consumer restarts, and coordinating partition redistribution when application instance counts change.

In Spring Kafka, `@KafkaListener` typically runs inside a listener container. The container manages the Kafka consumer, polls data, invokes the listener method, and commits offsets according to the configured acknowledgment mode. Operating durable consumers therefore requires understanding both Kafka consumer group behavior and how Spring Kafka manages commits.

## 1. What Is a Consumer Group?

A consumer group is a collection of consumers sharing the same `group.id`. Kafka treats them as members collaborating to process data from subscribed topics. For each partition, at most one consumer within the same group is assigned to read that partition at any given time. Different groups can read the same topic independently.

Example of an `orders` topic with four partitions and a `billing` service running three consumers in group `billing-service`:

```text
Topic orders
  Partition 0  --------------------> Consumer A
  Partition 1  --------------------> Consumer B
  Partition 2  --------------------> Consumer C
  Partition 3  --------------------> Consumer A

Consumer group: billing-service
```

Consumer A is assigned two partitions; B and C each get one partition. If the group scales to four consumers, each consumer can receive one partition. If six consumers run while the topic still has only four partitions, at least two consumers will receive no partition assignment and will not read from that topic.

Key principles:

- Consumers with the same `group.id` split partition processing and share reading progress.
- Consumers in different groups have independent offsets, so they can read the same data for separate purposes.
- A partition is assigned to at most one consumer in the same group at a time, but can be read concurrently by consumers in different groups.
- The number of useful consumers in a group is bounded by the number of partitions assignable to the group.
- Record ordering is guaranteed within a single partition. There is no global ordering across multiple partitions.

For example, `billing-service` and `analytics-service` can both read the `orders` topic using two different group IDs. Billing processes payments; analytics computes reports. Billing committing offsets does not cause analytics to skip data, because each group maintains its own progress.

## 2. Group ID and Scope of Reading Progress

`group.id` is the identifier of a consumer group and also the key Kafka uses to store reading progress. In Spring Kafka, you can set a default group ID on the consumer factory or override it per listener via the `groupId` attribute.

```properties
spring.kafka.consumer.group-id=billing-service
```

```java
@KafkaListener(topics = "orders")
public void handle(OrderCreated event) {
    billingService.process(event);
}
```

The listener above uses the consumer factory's default group ID. You can explicitly declare a separate group for a listener:

```java
@KafkaListener(topics = "orders", groupId = "invoice-service")
public void handleInvoice(OrderCreated event) {
    invoiceService.createInvoice(event);
}
```

If multiple listeners read the same topic and should share load, they must join the same group. If each listener needs to receive all records independently, they must use different group IDs. Accidentally sharing the same group ID between two applications with independent purposes causes them to split records, leaving each application seeing only a subset of the data.

The group ID should remain stable across restarts and deployments. Changing the group ID usually starts a fresh reading progress track. If the new group has no committed offset yet, `auto.offset.reset` decides where to start. Consequently, changing a group ID can cause the application to re-read large amounts of data or skip older data depending on the reset setting.

## 3. Partition Assignment and Rebalance

The Kafka group coordinator manages membership and partition distribution across group members. When a consumer joins, leaves the group, loses heartbeats, changes subscriptions, or when topic partition counts change, Kafka can perform a **rebalance** to redistribute partitions.

Example of a group initially having two consumers and four partitions:

```text
Before rebalance:
  Consumer A: P0, P1
  Consumer B: P2, P3

Consumer C joins group

After rebalance:
  Consumer A: P0, P1
  Consumer B: P2
  Consumer C: P3
```

During a rebalance, reading may pause or be interrupted depending on the assignment strategy and group protocol in use. The container must handle revoking old partitions, finishing or stopping in-flight work per policy, and then resuming with the new assignment. Frequent rebalances can reduce throughput, increase consumer lag, and increase the likelihood of records being reprocessed.

Common causes include:

- Application instances repeatedly restarting or failing health checks.
- A listener taking longer to process a batch than `max.poll.interval.ms`.
- Consumers failing to send heartbeats on time due to network issues, CPU saturation, or blocked consumer threads.
- Changes in instance count, topic subscriptions, or topic partition counts.
- Processing errors causing the container to repeatedly stop and restart.

Kafka supports different assignment strategies. The range assignor distributes partitions per topic in contiguous ranges; round-robin distributes cyclically; cooperative sticky tries to keep assignments stable and migrate only necessary partitions via cooperative rebalancing. Exact behavior depends on client configuration and Kafka version. Do not assume all rebalances stop all consumers for the same duration or always preserve existing assignments.

In Spring Kafka, you can configure the number of consumer threads on a listener container via `concurrency`. This is the number of consumers created inside each application instance for that listener, not the partition count. Increasing concurrency only helps when the group still has partitions to assign and downstream systems have spare capacity.

```java
@KafkaListener(
        topics = "orders",
        groupId = "billing-service",
        concurrency = "3")
public void handle(OrderCreated event) {
    billingService.process(event);
}
```

With three partitions, concurrency higher than three generally does not increase parallel processing for this listener. When subscribing to multiple topics, the total partition count and assignment rules determine actual parallelism.

## 4. Offsets and Committed Offsets

Every record in a partition has a monotonically increasing offset. An offset is the record's position within that partition, not a global cluster-wide ID.

Example of partition 0 containing records:

| Partition | Offset | Illustrative Content |
|---|---:|---|
| P0 | 100 | Order A created |
| P0 | 101 | Order B created |
| P0 | 102 | Order C created |
| P0 | 103 | Order D created |
| P0 | 104 | Order E created |

A consumer group stores the committed offset for each topic-partition pair. The committed offset represents **the next position the consumer will read**, not the offset of the last processed record. If the application has successfully processed record offset `104`, the position to commit is typically `105`.

```text
Last processed record: offset 104
Committed offset:      105
Next record:           offset 105
```

This convention allows a consumer to resume from the very next position after a restart. When viewing admin tools that display committed offsets, remember that the value is typically one higher than the last processed offset.

Committed offsets are stored by Kafka per group and topic-partition in the internal topic `__consumer_offsets`. Applications do not need to build their own offset table in a database for Kafka to track read position. Commits can be performed automatically by the Kafka client or managed by the Spring Kafka listener container according to the acknowledgment mode.

### 4.1. Log End Offset and Consumer Lag

The log end offset (LEO) describes the end of the log, representing the next offset available to be written. Consumer lag is typically estimated as the difference between the log end offset and the group's committed offset on each partition:

```text
approximate lag = log end offset - committed offset
```

For example, if the log end offset is `1500` and the group's committed offset is `1200`, the lag is approximately `300` records. This measures the count of pending records relative to commit progress. It does not directly indicate how long the oldest record has been waiting, the current processing rate, or whether business side effects have completed.

With asynchronous processing or batch commits, the committed offset may trail records already processed in memory. Conversely, committing at the wrong time can place the committed offset ahead of unfinished records and lose work. Therefore, inspect lag alongside processing rate, oldest unprocessed record age, processing errors, and business metrics.

## 5. When Does a Consumer Commit Offsets?

Committing an offset is the operation that persists the group's read progress to Kafka. The commit point determines which records may be redelivered after a consumer stops or a partition moves to another member.

There are two main management approaches:

- **Auto commit:** The Kafka consumer client periodically commits the current position per `auto.commit.interval.ms` when `enable.auto.commit=true`.
- **Manual/container-managed commit:** The application or Spring Kafka listener container decides when to commit after processing records according to the acknowledgment mode.

Auto commit is simple to configure, but it can commit polled positions before the application finishes processing every record in the batch. If the consumer stops after committing but before finishing processing, those records may not be redelivered to the group. For critical business processing, it is usually best to disable auto commit and let the listener container manage commits.

## 6. Acknowledgment Modes in Spring Kafka

The Spring Kafka listener container provides several acknowledgment modes to control when offsets are committed. Since Spring Kafka 2.3, the framework defaults `enable.auto.commit=false` unless explicitly configured otherwise; still, declare it explicitly to avoid confusion when reading application properties.

Basic configuration example:

```properties
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.consumer.auto-offset-reset=earliest
spring.kafka.listener.ack-mode=record
```

Common modes:

| Ack mode | Commit Timing | Best Suited When |
|---|---|---|
| `RECORD` | After the listener successfully processes each record | You want commit progress closely tracking each record and the listener processes one record at a time |
| `BATCH` | After all records from a poll are successfully processed | You want fewer commits and accept partial batch replay on failure |
| `TIME` | When the configured commit interval elapses and the batch has been processed | You want to bound commit frequency by time |
| `COUNT` | When the processed record count threshold is reached and the batch has been processed | You want to commit based on record count |
| `COUNT_TIME` | When either count or time condition is met and the batch has been processed | You want to combine both thresholds |
| `MANUAL` | Listener calls acknowledge; container commits per batch-completion rules | You want the listener to decide when a record is considered processed |
| `MANUAL_IMMEDIATE` | Listener calls acknowledge and container commits immediately when possible, especially on the consumer thread | You need tight control over when each acknowledgment commits |

`RECORD` and `BATCH` are common choices for synchronous listeners. `RECORD` limits how many records may need replaying after a single-record failure, at the cost of more commits. `BATCH` reduces commit overhead, but if a batch holds many records and the listener fails before finishing the batch, previously processed records may be redelivered.

With manual acknowledgment, only call `acknowledge()` after required business processing succeeds. Calling acknowledge before writing to a database or succeeding on a target service can cause the consumer to commit the offset and stop, preventing Kafka from redelivering the record even though the side effect never completed.

### 6.1. Listener Example with Per-Record Commit

```java
@KafkaListener(topics = "orders", groupId = "billing-service")
public void handle(OrderCreated event) {
    billingService.applyIdempotently(event);
}
```

Combined with `spring.kafka.listener.ack-mode=record`, the container commits the offset after the listener processes each record successfully. If the listener throws an exception, the container routes the error to the configured error handler and does not treat the record as successfully processed in the normal commit path.

`applyIdempotently()` represents a business operation safe to re-execute, such as inserting the event ID into an inbox table with a unique constraint inside the same database transaction as updating the order state. This handles the case where the side effect finished but the process stopped before committing the offset.

### 6.2. Manual Acknowledgment Example

When the listener needs to explicitly decide when to acknowledge, you can use `Acknowledgment`:

```properties
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.listener.ack-mode=manual
```

```java
@KafkaListener(topics = "orders", groupId = "billing-service")
public void handle(OrderCreated event, Acknowledgment acknowledgment) {
    billingService.applyIdempotently(event);
    acknowledgment.acknowledge();
}
```

In this example, the listener acknowledges only after `applyIdempotently()` finishes. If the business method throws an exception, the acknowledge line does not run and the container handles the error per configuration. With `MANUAL`, acknowledgments are coordinated by the container per batch rules; if immediate commit at acknowledgment time is needed, consider `MANUAL_IMMEDIATE` and ensure acknowledgment is invoked on the proper thread per Spring Kafka requirements.

Never combine Kafka client auto commit with manual offset commits inside the listener. Pick one consistent management mechanism to prevent two commit paths from competing.

## 7. Delivery Semantics and Consequences of Commit Timing

When business processing occurs relative to offset commits determines the risk of record loss or duplicate processing.

### 7.1. At-most-once

Commit the offset before executing side effects. If the consumer stops after committing but before processing, Kafka resumes from the new offset and the record never produces a business outcome. This reduces duplicate processing risk but can lose processing.

```text
Poll record
   |
   v
Commit offset
   |
   v
Execute business work
```

### 7.2. At-least-once

Execute business work first and commit the offset afterward. If the consumer stops after side effects finish but before committing, Kafka can redeliver the record after the group recovers. Hence, a record may be processed multiple times. This is the standard choice when avoiding lost events and side effects can be made idempotent.

```text
Poll record
   |
   v
Business work succeeds
   |
   v
Commit offset
```

### 7.3. Exactly-once in Kafka

Kafka transactions can combine producing output records and committing input record offsets in a single Kafka transaction. With consumers reading at `isolation.level=read_committed`, Kafka-to-Kafka pipelines can achieve exactly-once semantics within properly configured transactional boundaries.

Kafka's exactly-once does not automatically span databases, HTTP APIs, emails, or external systems. If a listener updates a database and then commits a Kafka offset, those two operations can still occur at separate points. For side effects outside Kafka, design idempotency, inbox/outbox patterns, or appropriate transactional coordination.

| Order | If Consumer Stops Between Steps | Consequence |
|---|---|---|
| Commit then process | Stops after commit | Side effect for the record may be lost |
| Process then commit | Stops after processing | Record may be reprocessed |
| Kafka transaction with output and input offset | Transaction aborts or commits atomically | Output and input progress stay consistent within the Kafka transaction |

## 8. `auto.offset.reset` and Groups Without Offsets

`auto.offset.reset` determines behavior when a group has no valid committed offset for a partition, or when the committed offset is no longer in the log due to retention. This property never overrides an existing valid committed offset.

Common options:

- `earliest`: start from the earliest offset still retained in the partition.
- `latest`: start from the current end of the log, skipping older records without a group-recorded offset.
- `none`: throw an error if no valid offset is found instead of automatically picking a starting position.

Example:

```properties
spring.kafka.consumer.auto-offset-reset=earliest
```

`earliest` is useful when a new group needs to read retained historical data. `latest` often suits streams only interested in new events produced after the consumer starts, though it can cause the application to miss pre-existing records when the group has no offset. `none` is appropriate when operations must explicitly decide the starting position instead of resetting automatically.

For example, group `billing-v2` has never read topic `orders`, which currently has offsets 0 through 999. With `earliest`, the group starts at the earliest remaining offset; with `latest`, the group starts at the log end and receives only subsequent records. If group `billing-service` already has a valid committed offset of 700, changing `auto.offset.reset` will not cause the group to jump back to 0 or forward to 999.

When a committed offset is expired out of the log by retention, Kafka may apply `auto.offset.reset`. This can create an unrecoverable gap of records from the topic. Retention must therefore exceed the maximum anticipated outage and backlog recovery duration.

## 9. Commit Failures, Rebalances, and In-Flight Records

Commits can fail if a consumer loses connectivity, the group is rebalancing, or an old member is no longer valid to commit. When a partition is revoked, the consumer must stop taking new work from that partition and handle already-polled records safely.

Never assume a successful client-side commit call always means the offset is durably persisted. With async commits, callbacks may report errors after the application has already moved on. With sync commits, the application waits for a broker response and must handle timeouts or exceptions. The Spring Kafka listener container manages commits per acknowledgment mode and error handler; avoid calling `consumer.commitSync()` manually from a listener method without a clear design.

Settings affecting group stability:

```properties
spring.kafka.consumer.properties[max.poll.records]=100
spring.kafka.consumer.properties[max.poll.interval.ms]=300000
spring.kafka.consumer.properties[session.timeout.ms]=45000
```

These are illustrative values, not fixed recommendations for every application. `max.poll.records` bounds records returned in one poll. `max.poll.interval.ms` bounds the time between polls; if batch processing takes longer, the consumer can be evicted and partitions reassigned. `session.timeout.ms` participates in disconnected-consumer detection alongside heartbeats. Tune based on high-load processing times, heartbeat settings, and Kafka cluster limits.

If a listener processes asynchronously or hands records to another executor, never commit offsets just because records were placed into an internal queue. In-memory queues lose data if the process crashes. Only acknowledge once the work reaches the committed completion point, or persist pending work state durably.

## 10. Observing Consumer Groups and Committed Offsets

Operations must observe membership, assignments, commit progress, and processing latency. Useful signals include:

- Current member count in the group and group state.
- Partitions assigned to each consumer.
- Committed offset and log end offset per partition.
- Consumer lag by group and by partition.
- Rebalance count, rebalance duration, and commit errors.
- Records processed per second, processing duration, and oldest unprocessed record age.
- Listener error rate, retries, and records routed to DLT.

Steadily rising consumer lag can indicate consumers cannot keep pace with incoming data. Lag dropping to 0 does not guarantee business work completed if the application commits before side effects or runs unmanaged async processing. Correlate Kafka metrics with business metrics such as recorded orders, pending transactions, and time from event creation to event completion.

When investigating a group:

1. Confirm the exact `group.id`, topic, and environment under inspection.
2. Check group state, member count, and partition assignment.
3. Compare committed offsets against log end offsets for each partition.
4. Inspect processing rate, oldest record age, and listener errors.
5. Check rebalances, poll intervals, heartbeats, and downstream health.
6. After remediation, verify committed offsets advance and lag drains at the expected rate.

Do not rely solely on topic-wide total lag. One partition may be stalled while others process fast, allowing total lag to mask the issue. Inspect per-partition metrics and key distribution.

## 11. Controlled Offset Resets

Occasionally operations teams must replay data after fixing a bug or skip a range of records confirmed unnecessary to process. Changing committed offsets causes the group to re-read or skip records, making it an operational action with direct business impact.

Before resetting offsets:

- Identify the exact affected group, topic, and partitions.
- Decide whether the goal is replaying from an older offset or skipping ahead to a newer offset.
- Verify the consumer group is stopped or has no active members as required by the reset tool.
- Use dry-run mode to preview target offsets before executing.
- Confirm consumers process idempotently if replaying can repeat side effects.
- Record old and new offsets so decisions can be audited or reverted.

Resetting offsets backward can trigger duplicate processing; resetting forward can skip records. Never use offset resets as a routine cure for consumer lag when the true cause is throughput, downstream capacity, or rebalances. After resetting, monitor progress and reconcile business outcomes.

## 12. Operational Example: Consumer Restart Mid-Processing

Suppose group `billing-service` is processing partition 0. Record offset `104` was read and successfully updated in the database, but the process stopped before committing offset `105`.

```text
First run:
  poll offset 104
       |
       v
  database transaction succeeds
       |
       X process stops before commit

Next run:
  group reads old committed offset (104)
       |
       v
  record offset 104 is redelivered
       |
       v
  idempotency detects event already applied
       |
       v
  commit offset 105
```

This is a classic at-least-once scenario. Kafka ensures the record can be redelivered because progress was not committed; the application must ensure applying the event a second time does not create a duplicate payment or duplicate invoice. An inbox table with a unique constraint on `event_id` is one pattern: store the event ID and update business state in the same database transaction.

If the application committed offset `105` before updating the database and crashed right after committing, the record would not be redelivered under group progress even though the database saw no change. This is why commit timing must match business semantics.

## 13. Durable Consumer Group Design Checklist

Before taking a consumer into production, teams should align on and verify the following points:

1. Each business stream has a stable `group.id` with the right data-sharing scope.
2. Partition count and concurrency match desired throughput; do not scale consumers beyond partition or downstream capacity.
3. Partition assignment, rebalances, and causes of group instability are well understood.
4. Auto commit is disabled when tight acknowledgment control is required; acknowledgment mode matches how the listener processes.
5. Offsets are committed only after work is considered complete; duplicates are handled via idempotency under at-least-once.
6. `auto.offset.reset` is intentionally chosen for new groups or expired offsets.
7. Poll interval, max poll records, session timeout, and processing times are configured cohesively.
8. Committed offsets, log end offsets, per-partition lag, rebalances, and commit failures are monitored.
9. Controlled procedures exist for offset resets, replays, and reconciliation.
10. For side effects outside Kafka, inbox/outbox or appropriate consistency mechanisms are designed; never assume Kafka transactions cover databases or HTTP.

The consumer group determines who shares partition reading; the committed offset determines where the group resumes reading. When both are designed alongside acknowledgments and idempotent processing, Spring Kafka applications can recover from restarts, rebalances, and downstream failures while keeping duplicates, lost work, and business latency under control.

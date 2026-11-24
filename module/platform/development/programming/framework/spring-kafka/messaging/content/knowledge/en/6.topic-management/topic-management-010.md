# Changing Partitions and Related Limitations

## 1. Why Change the Partition Count?

A partition is the unit of storage and parallel processing of a Kafka topic. Each partition is an ordered log processed by at most one consumer within the same consumer group at any given time. Therefore, the partition count directly affects load distribution, consumer parallelism, and how Kafka stores data.

When traffic grows, more consumers need to run concurrently, or one partition becomes a hotspot, teams may consider increasing the partition count. For example, an `orders` topic initially has 3 partitions and a consumer group has 3 active consumers. If more consumers are needed to increase parallel processing capacity, the topic can be expanded to 6 partitions.

However, increasing partitions is an architectural change to the data stream. It affects key-based partitioning, event ordering, consumer groups, broker resources, and operations. Evaluate these impacts before modifying a production topic.

## 2. What Changes When Increasing Partitions?

Suppose the `orders` topic has 3 partitions:

```text
Before scaling

Topic: orders
  Partition 0  ── Consumer A
  Partition 1  ── Consumer B
  Partition 2  ── Consumer C

After increasing to 6 partitions

Topic: orders
  Partition 0  ──┐
  Partition 1  ──┤
  Partition 2  ──┼── Consumer group: order-service
  Partition 3  ──┤       Consumer A, B, C, D, E, F
  Partition 4  ──┤       reassigned after rebalance
  Partition 5  ──┘
```

When increasing partitions:

- Kafka creates new partitions with their own logs and offsets.
- Existing records remain in the old partitions; Kafka does not automatically redistribute historical data into the new partitions.
- New partitions typically start empty; producers write new data to them according to the partitioner or explicit partition assignment.
- Consumer groups may rebalance to assign the new partitions to consumers.
- Committed offsets for old partitions remain tied to those partitions; new partitions without committed offsets follow initialization policies such as `auto.offset.reset`.

Increasing partitions does not mean increasing the replication factor. Each new partition is created according to the topic's replication configuration and cluster assignment; the number of replicas per partition is separate from the partition count.

## 3. Crucial Limitation: Only Increase, Never Decrease Partitions

Kafka supports increasing the partition count of an existing topic. There is no standard alter-topic operation to decrease the partition count. For instance, a topic with 12 partitions cannot be changed directly down to 6 partitions via `kafka-topics.sh --alter`.

The reason is that each partition maintains its own log, offsets, and distribution state. Removing partitions would require deciding which data to discard, which offsets to preserve, and how to handle consumer groups tracking those partitions. Consequently, Kafka provides no direct decrease-partition operation.

If fewer partitions are required, the safe approach is usually to create a new topic with the desired partition count, then plan a migration of producers and consumers to the new topic. The migration must specify how to copy or replay required data, cutover timing, starting offsets, duplicate handling, and how long to retain the old topic. Do not arbitrarily delete and recreate a topic with the same name, as that can cause data loss, change topic identity, and trigger unexpected behavior in running consumer groups or applications.

## 4. Impact on Message Keys and Event Ordering

This is the most critical impact when increasing partitions on a topic that uses message keys.

With the default partitioner and keyed records, Kafka generally selects a partition based on a hash of the key and the current partition count. You can visualize this simply as:

```text
partition = hash(key) % partitionCount
```

Suppose `orderId=ORD-100` previously routed to partition 1 when the topic had 3 partitions. After increasing the topic to 6 partitions, the mapping may route new records for `ORD-100` to a different partition. Older records stay in partition 1, while newer records may land in a new partition.

```text
Before increasing partitions:
  ORD-100 / OrderCreated  ──▶ Partition 1
  ORD-100 / OrderPaid     ──▶ Partition 1

After increasing partitions (e.g., key mapped to partition 4):
  ORD-100 / OrderCreated  ──▶ Partition 1  (historical record)
  ORD-100 / OrderPaid     ──▶ Partition 4  (new record)
```

Kafka only guarantees ordering within a single partition. If events for the same order sit across two partitions, two consumers may process them concurrently and completion order is no longer guaranteed. Thus, increasing partitions can break the assumption that "the same key is always processed sequentially" across the change boundary.

How the mapping shifts depends on the partitioner. With a custom partitioner, the strategy may differ; with keyless records, the partitioner may use sticky batching. Regardless of approach, verify actual routing behavior instead of assuming every key keeps its old partition.

If business logic strictly requires ordering for a single entity, evaluate the risks before increasing partitions. Options include:

- Accepting a controlled cutover: pause producers, wait for consumers to drain existing data, change the partition count, then resume publishing. This still requires verifying key mapping and when consumers restart.
- Creating a new versioned topic with the target partition count, migrating data and producers under a controlled workflow.
- Designing stable routing using a fixed number of logical shards or a custom partitioner when long-term stability is required; such a solution must be designed and tested from the outset.

Global ordering cannot be restored simply by adding more consumers or changing concurrency.

## 5. Impact on Consumer Groups and Concurrency

Within a consumer group, each partition at any given time is assigned to at most one consumer. One consumer can receive multiple partitions, but one partition is never processed concurrently by multiple consumers in the same group.

Therefore, partition count sets an upper bound on how many consumers can run concurrently in a single group for that topic. Examples:

| Partitions | Consumers in Group | Result |
|---:|---:|---|
| 3 | 2 | Two consumers share the 3 partitions |
| 3 | 3 | Possible to have one partition per consumer |
| 3 | 5 | At most 3 consumers receive partitions; remaining consumers stay idle |
| 6 | 6 | 6 partitions can be distributed across 6 consumers |
| 6 | 3 | Each consumer can receive multiple partitions |

When partitions increase, the consumer group may trigger a rebalance to redistribute assignments. During a rebalance, reading may pause or slow down depending on the assignor and group protocol. New instances do not necessarily receive identical numbers of partitions if subscriptions or assignment constraints apply.

In Spring Kafka, `concurrency` on the listener container factory or `@KafkaListener` controls how many consumers an endpoint can spawn. Raising `concurrency` past the number of assigned partitions does not increase useful parallelism. Coordinate partition count, application instance count, concurrency, and per-record processing time.

## 6. Increasing Partitions with Kafka CLI

Before making changes, inspect the current topic:

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders
```

The output shows partition count, replication factor, leaders, replicas, and ISR. Record the pre-change state for post-operation comparison.

Example increasing the `orders` topic from 3 to 6 partitions:

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --alter \
  --topic orders \
  --partitions 6
```

The `--partitions` flag specifies the **total partition count after the change**, not the number of partitions to add. If the topic currently has 3 partitions and you want to add 3 more, pass `6`, not `3` or `9`.

Verify afterward:

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders
```

Confirm the new partition count, leaders, and replica assignments for each partition. Monitor ISR to ensure replicas catch up. On Windows, the script name may be `kafka-topics.bat` depending on the Kafka package installed.

## 7. Increasing Partitions with the Admin API

Java applications can use the Kafka Admin API to increase partitions. `NewPartitions.increaseTo()` takes the target partition count:

```java
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.admin.NewPartitions;

import java.util.Map;

public class TopicPartitionUpdater {

    public void increaseOrdersPartitions() throws Exception {
        Map<String, Object> config = Map.of(
                AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
                "localhost:9092");

        try (Admin admin = Admin.create(config)) {
            admin.createPartitions(Map.of(
                    "orders", NewPartitions.increaseTo(6)))
                    .all()
                    .get();
        }
    }
}
```

The call completes only once Kafka confirms the partition creation operation. In production applications, handle timeouts, authorization errors, missing topics, and cases where the target partition count is not greater than the current count. Avoid running partition-increase logic on every application startup unless you have explicit migration or idempotent governance mechanisms.

Spring Kafka's `KafkaAdmin` supports managing Kafka resources and initial topic declaration via `NewTopic`. When an active topic must be modified, you can invoke the Admin API intentionally within a separate administrative workflow while logging and verifying outcomes.

## 8. Declaring Partition Count at Topic Creation with Spring Kafka

If parallelism needs are known upfront, declare the right partition count when creating the topic. Example:

```java
@Configuration
public class KafkaTopicConfiguration {

    @Bean
    NewTopic ordersTopic() {
        return TopicBuilder.name("orders")
                .partitions(6)
                .replicas(3)
                .build();
    }
}
```

`partitions(6)` sets the desired partition count at topic creation; `replicas(3)` sets the replication factor. The cluster needs enough brokers to distribute replicas. For existing topics, verify the behavior of your Spring Kafka version; do not assume changing numbers in the bean will automatically move historical data or reduce partitions.

Partition count should be treated as a design decision with long-term impact. Base it on measured throughput, desired parallelism, expected consumer count, key cardinality, ordering requirements, and broker capacity.

## 9. Resource Limits When Increasing Partitions

Each additional partition creates extra logs, metadata, and management work. With a replication factor of 3, one new partition creates three replicas across the cluster. Therefore, increasing partitions increases costs for both brokers and management systems.

Limits to evaluate:

| Factor | Impact as Partitions Increase | What to Check |
|---|---|---|
| Files and log segments | More partitions create more directories/log segments and file handles | File descriptor limits, disk space, segment counts, and retention policies |
| Memory and metadata | Brokers, controller, and clients must track more partitions/leaders/replicas | Heap usage, metadata size, metadata update latency, and controller load |
| Replication | Each partition has followers fetching and maintaining ISR | Network bandwidth, disk I/O, under-replicated partitions, and ISR shrinks |
| Leaders and request handling | More leaders/partitions increase coordination and request overhead | Leader balance, CPU, request rates, and latency per broker |
| Recovery and rebalancing | Broker startup, replica recovery, and partition assignment can take longer | Restart/recovery time, rebalance duration, and consumer lag |
| Consumers | More partitions can raise parallelism while also increasing poll/assignment cost | Consumer count, concurrency, processing time, and per-partition lag |

There is no single maximum partition count that fits every Kafka cluster. Practical limits depend on Kafka version, broker configuration, hardware, workload, replication factor, and operations. Do not increase partitions simply to spawn more consumers without first measuring the current bottleneck.

## 10. Planning Partition Counts

When designing a topic, start from throughput requirements and the processing capacity of each partition in a realistic environment.

An initial estimate:

```text
Required partitions ≈
    target topic throughput
    --------------------------------
    safe measured throughput per partition
```

This is only an initial estimate. Run load tests to determine safe throughput considering record size, producer count, consumer count, replication, disk, and network. Then add headroom for growth, maintenance, and traffic fluctuations.

Beyond throughput, answer these questions:

1. How many consumers need to process concurrently within one group?
2. Are keys evenly distributed, or do a few keys account for most of the traffic?
3. Does the business require ordering by `orderId`, `accountId`, or another entity key?
4. Are there enough brokers and racks to distribute replicas?
5. Will the new partition count push metadata, recovery, and monitoring costs past cluster capacity?
6. Is there a plan for future partition increases and a procedure to handle key-mapping changes?

If a single key generates most of the traffic, increasing partitions may not resolve the hotspot because all records with that key still route by the same rule. Re-evaluate the key choice, partitioning model, or split the business stream appropriately; do not break ordering merely to spread load.

## 11. Increasing Partitions Differs from Partition Reassignment

Two operations are frequently confused:

| Operation | Purpose | Does Old Data Move? |
|---|---|---|
| Increasing partition count | Adds new partitions to a topic to expand parallelism and key distribution | No; historical records stay in old partitions |
| Partition reassignment | Moves replicas of existing partitions to other brokers or changes replica placement | Can copy replica data across brokers; does not change partition count |

If the problem is that one broker holds too many replicas or leaders, increasing partitions will not necessarily solve it. Consider reassignment and leader balancing instead. Conversely, if a consumer group needs greater parallelism, reassignment does not increase the partition count.

After increasing partitions, Kafka can distribute replicas of the new partitions according to the generated assignment. Existing partitions retain their current assignment unless a separate reassignment operation runs.

## 12. Safe Partition-Change Workflow

Before executing in production, prepare an observable and controlled change:

1. **Assess the need:** measure producer throughput, consumer lag, processing time, hot partitions, and active consumer count.
2. **Check ordering:** identify which keys require ordering; assess whether increasing partitions alters key mapping.
3. **Check cluster health:** verify brokers are online, leaders are stable, ISRs are full, and disk/network headroom is available.
4. **Pick target partition count:** calculate from throughput and expected concurrency, plus reasonable headroom.
5. **Plan the change:** schedule the timing, account for rebalance impact, notify consumer owners, and prepare rollback/mitigation steps if issues arise.
6. **Execute partition increase:** use CLI or Admin API with the target partition count.
7. **Verify:** describe the topic, inspect leaders/replicas/ISR, and observe consumer groups and producer routing.
8. **Monitor post-change:** watch consumer lag, throughput, latency, rebalances, under-replicated partitions, and load distribution.

If per-key ordering is mandatory, establish a dedicated cutover plan before allowing producers to write into new partitions. Increasing partitions directly while producers continue publishing can place events for the same key into different partitions.

## 13. Summary

- A partition is the ordered log unit and the fundamental unit of parallelism for a consumer group.
- Kafka supports increasing partition counts but does not support decreasing them directly.
- Increasing partitions creates new logs; historical data is not automatically redistributed.
- With the default partitioner, changing partition counts can alter key mapping, affecting ordering for events sharing a key across the scaling boundary.
- Within a consumer group, a partition is assigned to at most one consumer at a time; partition count caps useful parallelism.
- Raising partition counts increases metadata, log, file handle, replication, recovery, and rebalance overhead.
- Increasing partitions differs from reassignment; choose the operation matching the bottleneck being solved.
- Measure load, verify ordering, check broker health, and monitor after changes before scaling production topics.

In Spring Kafka, `KafkaTemplate` continues routing records according to the configured partitioner and key, while listener containers receive partitions assigned by the consumer group. Understanding the effects of changing partitions helps design topics that scale while preserving correctness across event streams.

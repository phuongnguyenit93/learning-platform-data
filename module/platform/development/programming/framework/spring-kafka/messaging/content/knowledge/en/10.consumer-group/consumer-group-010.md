# Balancing Consumer Count and Partition Count

## 1. Why Must Consumers and Partitions Be Balanced?

In Kafka, a partition is the fundamental unit of parallelism for a consumer group. At any given time, a partition is assigned to at most one consumer member within the same group. A single consumer can receive multiple partitions, but multiple consumers in the same group cannot concurrently read the same partition under the standard assignment mechanism.

Therefore, the number of partitions caps the useful parallelism of a consumer group. If there are fewer consumers than partitions, each consumer handles multiple partitions. If the consumer count equals the partition count, the group can distribute at roughly one consumer per partition. If there are more consumers than partitions, some consumers will receive no partitions and remain idle with respect to that topic.

Choosing the right consumer count balances throughput, latency, application resources, and rebalance overhead. Merely adding consumers does not guarantee faster processing; you must look at partition counts, load per partition, and each consumer's actual processing capacity.

## 2. Basic Rules Between Consumer Count and Partition Count

Assume all consumers in the group subscribe to the same topic with the same subscription scope. Let:

- `P`: number of partitions in the topic.
- `C`: number of active consumer members in the group.

The maximum partition-level parallelism can be estimated as:

\[
\text{Max consumers assigned a partition} = \min(P, C)
\]

If `C > P`, the number of consumers that may remain unassigned is:

\[
\text{Idle consumers} = \max(C - P, 0)
\]

This is the general rule for a single topic with identical subscriptions. When a group subscribes to multiple topics, count the total partitions the group actually receives in assignments; the assignor, subscriptions, and specific configuration determine the final distribution.

### Fewer Consumers Than Partitions

For example, the `orders` topic has 12 partitions and the `order-service` group has 4 consumers:

```text
Topic orders: P = 12
Consumer group: C = 4

Consumer A  ◀── P0, P1, P2
Consumer B  ◀── P3, P4, P5
Consumer C  ◀── P6, P7, P8
Consumer D  ◀── P9, P10, P11
```

Each consumer handles roughly 3 partitions if the assignment distributes evenly. Partitions are still processed in parallel across the four consumers; inside each consumer, the listener container polls data from its assigned partitions.

### Equal Consumers and Partitions

If the topic has 12 partitions and the group has 12 consumers:

```text
P0  ──▶ Consumer A
P1  ──▶ Consumer B
P2  ──▶ Consumer C
P3  ──▶ Consumer D
P4  ──▶ Consumer E
P5  ──▶ Consumer F
P6  ──▶ Consumer G
P7  ──▶ Consumer H
P8  ──▶ Consumer I
P9  ──▶ Consumer J
P10 ──▶ Consumer K
P11 ──▶ Consumer L
```

For a single topic and consumers with identical subscriptions, the group can assign one partition to each consumer. This is the maximum parallelism bounded by the topic's partition count.

### More Consumers Than Partitions

If the topic has 12 partitions but the group has 16 consumers:

```text
P0..P11 ──▶ 12 consumers assigned partitions

Consumer M ── idle
Consumer N ── idle
Consumer O ── idle
Consumer P ── idle
```

At most 12 consumers have partitions to process this topic at a time. The remaining four consumers add no parallel reading capacity. They can still participate in the group and add membership, heartbeat, or rebalance overhead depending on configuration.

## 3. Quick Comparison Table

| Partitions (`P`) | Consumers (`C`) | Max assigned consumers | Notes |
|---:|---:|---:|---|
| 12 | 3 | 3 | Each consumer receives roughly 4 partitions |
| 12 | 6 | 6 | Each consumer receives roughly 2 partitions |
| 12 | 12 | 12 | Can achieve a 1 consumer/partition ratio |
| 12 | 16 | 12 | Up to 4 consumers may remain idle |
| 4 | 2 | 2 | Each consumer receives roughly 2 partitions |
| 4 | 4 | 4 | Can distribute 1 partition per consumer |
| 4 | 8 | 4 | Up to 4 consumers may remain idle |

The "roughly" numbers assume a relatively even assignment. Do not treat this table as a guarantee that every consumer always gets the exact same number of partitions; actual results also depend on the partition assignor, topic count, and each member's subscriptions.

## 4. How Can One Consumer Handle Multiple Partitions?

A Kafka consumer calls `poll()` to fetch records from all currently assigned partitions. A single consumer can receive records from multiple partitions within one poll. Spring Kafka's listener container manages the poll loop and dispatches records to the listener.

For example, Consumer B is assigned partitions 3, 4, and 5:

```text
Consumer B
   |
   +── poll()
        |
        +── orders-3: offset 20, 21
        +── orders-4: offset 80, 81
        +── orders-5: offset 12, 13
```

Partitions have independent offsets. Offset `21` of `orders-3` is unrelated to offset `81` of `orders-4`. The consumer group stores committed offsets per topic-partition pair.

In standard listener processing, the container invokes the listener for polled records according to container rules. Kafka guarantees order within each individual partition, with no global order across partitions. If the application hands records off to an executor for parallel processing, it must manage completion order and commit boundaries for each partition itself.

## 5. Multiple Topics: Count Total Subscribed Partitions

A consumer group can subscribe to multiple topics. In that case, parallelism is governed by the partition count across the entire subscription that the group receives in assignments, not just the partition count of a single topic.

For example, the `notification-service` group subscribes to:

| Topic | Partitions |
|---|---:|
| `orders` | 6 |
| `payments` | 4 |
| `shipments` | 2 |
| **Total** | **12** |

If all 8 consumers subscribe to all three topics together, there are 12 partitions in total to distribute. The group can assign partitions to all 8 consumers; on average each consumer receives roughly 1 to 2 partitions. If scaled to 14 consumers, at most 12 consumers receive assignments and at least 2 consumers may stay idle.

If consumers have differing subscriptions, you cannot simply take total partitions and divide evenly. For example, if some members subscribe only to `orders` while others subscribe to all three topics, the assignor must respect the partition set each member is eligible to receive. Inspect the actual assignment.

## 6. The Partition Assignor Determines Distribution

Kafka uses a partition assignor to distribute partitions among consumer members in the group. The assignor affects how evenly partitions are divided and how many partitions must change owners when group membership changes.

Common assignors in the Kafka client:

| Assignor | High-level characteristics |
|---|---|
| `RangeAssignor` | Splits partitions per topic into contiguous ranges for consumers; across multiple topics, can produce uneven distribution across members |
| `RoundRobinAssignor` | Distributes partitions round-robin across eligible consumers; usually balances well when members share subscriptions |
| `StickyAssignor` | Tries to distribute evenly and preserve old assignments as much as possible to minimize partition movement |
| `CooperativeStickyAssignor` | Combines stickiness with cooperative/incremental rebalancing to avoid revoking all assignments at once |

Assignor names can be configured via `partition.assignment.strategy`; available choices and rebalance protocols depend on the Kafka client and broker versions. Do not change the assignor in production without checking compatibility and rollout behavior across the entire consumer group.

### Multi-Topic Distribution Example

Suppose a group has three consumers all subscribing to two topics: `orders` with 3 partitions and `payments` with 2 partitions. With `RangeAssignor`, assignments are computed per topic. A possible outcome is:

```text
Consumer A: orders-0, payments-0
Consumer B: orders-1, payments-1
Consumer C: orders-2
```

Consumers A and B receive two partitions, while Consumer C receives one partition. This illustrates how distribution can skew when each topic's partition count does not divide evenly by the member count. Other assignors may spread partitions differently. Inspect actual assignments instead of assuming every assignor splits total partitions evenly.

## 7. Consumer Count in Spring Kafka

In Spring Kafka, each listener container manages one or more Kafka consumers. There are two common ways to increase the number of consumer members:

- Increase the number of application instances (e.g., pods or processes).
- Increase the listener container's `concurrency`.

Example configuring concurrency using `ConcurrentKafkaListenerContainerFactory`:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    ordersListenerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        return factory;
    }
}
```

The listener uses the factory:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "ordersListenerFactory")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
```

Or set concurrency directly on the annotation:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        concurrency = "3")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
```

With one endpoint, one application instance, and `concurrency=3`, the listener container creates three consumers. If three application instances run the same endpoint and each instance has concurrency 3, the group can have 9 consumer members in total. Calculate the actual consumer count across the entire deployment, not just by looking at one instance's configuration.

`concurrency` is the number of consumers the container creates for the endpoint. It does not create new partitions. If the topic has 4 partitions while the whole deployment has 8 consumers in the same group, at most 4 consumers are assigned partitions of the topic at a time.

## 8. Calculating Effective Consumer Count in a Deployment

For a listener endpoint deployed uniformly across multiple instances, you can estimate:

\[
C_{total} = N_{instances} \times concurrency
\]

Examples:

| Application instances | Concurrency per instance | Total consumer members |
|---:|---:|---:|
| 1 | 2 | 2 |
| 2 | 2 | 4 |
| 3 | 2 | 6 |
| 4 | 3 | 12 |

Suppose the `orders` topic has 6 partitions:

- 2 instances × concurrency 2 = 4 consumers: each consumer can receive roughly 1 to 2 partitions.
- 3 instances × concurrency 2 = 6 consumers: can achieve a 1 consumer/partition ratio.
- 4 instances × concurrency 3 = 12 consumers: at most 6 consumers receive partitions, and the remaining 6 consumers can stay idle.

This calculation applies to one endpoint and one group. If an application has multiple listener endpoints, multiple topics, or multiple group IDs, calculate membership and subscriptions separately for each group. Do not sum concurrency across different groups to compare against the partitions of a single group.

## 9. Sizing Consumers by Throughput, Not Just a 1:1 Ratio

A one-consumer-per-partition ratio is not always optimal. One consumer can handle multiple partitions if total traffic and processing duration still meet SLAs. Conversely, even one consumer per partition can lack capacity if records are heavy or the consumer must call multiple external systems.

Measure the following factors:

- **Producer throughput**: records/second and bytes/second written to the topic.
- **Consumer processing rate**: records/second each consumer sustains reliably with real payloads and business logic.
- **Processing latency**: average processing time, p95/p99, and dependent service call durations.
- **Partition skew**: whether load is distributed evenly across partitions; a hot key can overload one partition.
- **Consumer lag**: whether lag climbs continuously or only spikes briefly during peak hours.
- **Resource utilization**: CPU, heap, garbage collection, network, connection pools, and database load.
- **Poll/rebalance health**: intervals between polls, rebalance counts, and processing errors.

An initial estimate can use:

\[
\text{Required consumers} \approx
\frac{\text{Target throughput}}{\text{Safe throughput per consumer}}
\]

Then cap by the number of partitions assigned to the group. This is only an estimation step; load-test to measure safe throughput and add headroom for traffic spikes, broker maintenance, or temporary consumer failures.

For example, if a topic must process 24,000 records/second and each consumer has been measured at 4,000 records/second under SLA conditions, the estimate requires 6 active consumers. The topic needs at least 6 partitions with sufficiently balanced load for the group to utilize all 6 consumers. If the topic has only 3 partitions, raising concurrency to 6 does not create 6 useful parallel reading streams; evaluate adding partitions or changing the processing architecture.

## 10. Partition Skew and Hot Keys

Partition count and consumer count only create potential parallelism. If one partition receives most of the traffic, the consumer owning that partition can become overloaded while other consumers sit nearly idle.

For example, a topic has 8 partitions, but 60% of records use the same key `customerId=VIP-001`. If the partitioner routes this key to partition 3, most of the load concentrates on the single consumer owning partition 3. Increasing consumers from 8 to 16 does not split a single partition across multiple consumers in the same group.

Mitigations to consider:

- Measure key distribution and per-partition throughput to identify hot keys.
- Review keys against business ordering requirements; do not alter keys solely to balance load if doing so breaks required ordering.
- If business rules allow, subdivide workloads using controlled shard keys.
- Separate streams or topics for special workload tiers when clear business boundaries exist.
- Tune heavy processing logic, caching, or batching to increase throughput on the consumer owning the hot partition.

Adding partitions can change key mapping and the order of events sharing a key across the expansion boundary. If strict per-entity ordering is required, prepare a dedicated plan for changing partition counts and key mapping.

## 11. Rebalancing When Adding or Removing Consumers

When consumers join or leave a group, Kafka can rebalance to redistribute partitions. Common rebalance triggers:

- Scaling deployments up or down.
- A consumer process stopping, crashing, or losing connectivity.
- A consumer failing to poll within `max.poll.interval.ms`.
- Subscriptions or partition counts changing.
- The consumer group changing its assignment strategy or group protocol.

During a rebalance, partitions may be revoked and reassigned. Depending on the assignor and cooperative protocol, processing pauses and the number of partitions that must move will vary. Frequent rebalances can reduce throughput and increase lag.

Related properties:

| Property | Role |
|---|---|
| `max.poll.interval.ms` | Maximum time between `poll()` calls before the consumer is considered no longer making progress and may leave the group |
| `session.timeout.ms` | Duration the broker waits for heartbeats before considering the consumer disconnected (depending on group protocol and configuration) |
| `heartbeat.interval.ms` | Heartbeat cadence in consumer protocol configurations where this property applies |
| `max.poll.records` | Caps maximum records returned in a single poll; affects processing workload before the next poll |

Do not raise `max.poll.interval.ms` just to mask overly slow processing without measuring the cause. If listeners take too long, evaluate appropriate batch sizes, optimize business logic, offload heavy work, or manage asynchronous processing while keeping offset commits in proper order.

## 12. Preserving Order When One Consumer Receives Multiple Partitions

Kafka guarantees ordering within each partition. If one consumer receives multiple partitions, records within each partition retain their own order, but there is no global order across them.

For example, Consumer A receives `orders-0` and `orders-1`:

```text
orders-0:  A1 ── A2 ── A3
orders-1:  B1 ── B2 ── B3

No ordering guarantee between A1 and B1,
or between A2 and B2.
```

With sequential listener processing, the container processes records in poll/dispatch order appropriate for each partition. If the application hands work off to multiple threads, B1 can finish before A1 even though A1 was polled first. In that case, design ordering per partition or key, and only commit up to the contiguous completed offset within that partition.

Do not use consumer count as a way to create global ordering. If business rules require strict ordering for the entire topic, consider a single partition and a single processing stream, accepting the corresponding throughput limit.

## 13. Inspecting Assignments and Consumer Lag

### Checking a Topic's Partition Count

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders
```

The command displays partitions, leaders, replicas, and ISR. Note the total partition count before deciding to add consumers.

### Inspecting the Consumer Group

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-service
```

The output shows which partitions are assigned to which consumer members, consumer hosts, and per-partition lag. If there are more consumers than partitions, some members may not appear in partition rows because they own no partitions; use the member-detail mode of your Kafka version if you need to identify all idle members.

Do not look only at total lag. High lag on one partition while other partitions stay near zero often points to skew, a hot key, or an issue with a single consumer member. If lag rises on all partitions together, total consumer capacity may be lower than producer speed.

## 14. Process for Selecting and Tuning Consumer Count

A practical workflow can follow these steps:

1. **Count partitions:** determine the topic's partition count or the group's total subscription.
2. **Count effective consumers:** compute application instances multiplied by endpoint concurrency; verify the exact group ID.
3. **Measure load:** collect throughput, processing latency, per-partition lag, and CPU/memory/network resources.
4. **Find the bottleneck:** identify whether it is too few consumers, hot partitions, slow business logic, rebalances, or an overloaded downstream system.
5. **Scale consumers carefully:** increase or decrease instances/concurrency in steps and observe rebalances.
6. **Evaluate partitions:** if useful consumers hit the partition ceiling, consider adding partitions after evaluating key mapping and ordering.
7. **Test failure modes:** stop one consumer, verify partition reassignment, committed offsets, and redelivery handling.
8. **Lock in configuration:** document concurrency, instance count, partition count, assignor, and lag/SLA thresholds to monitor.

You do not need to force the consumer count to equal the partition count in every system. One consumer handling multiple partitions can be more efficient if throughput meets requirements and resources are utilized sensibly. The goal is sufficient processing capacity with acceptable latency and resilience when a member fails.

## 15. Summary

- Within a consumer group, a partition is assigned to at most one consumer member at a time.
- If there are fewer consumers than partitions, each consumer can receive multiple partitions; if there are more consumers than partitions, some consumers will be idle.
- For a single topic with identical subscriptions, maximum partition-level parallelism is `min(partition count, consumer count)`.
- When subscribing to multiple topics, sum all partitions eligible for assignment and account for subscriptions and the assignor.
- Spring Kafka scales consumers via application instances and `concurrency`; concurrency does not create new partitions.
- Throughput, partition skew, hot keys, processing time, and rebalances matter more than achieving a 1:1 ratio on paper.
- Adding consumers beyond the partition count adds no useful parallelism; scaling further requires evaluating partition counts and ordering.
- Always inspect assignments, lag, and resources after scaling.

When consumer count and partition count are balanced properly, a Spring Kafka application takes advantage of the parallelism a topic offers, avoids idle consumers, and maintains stable processing as load shifts.

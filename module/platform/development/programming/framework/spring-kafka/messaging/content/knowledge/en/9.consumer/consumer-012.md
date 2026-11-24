# Limits of a Consumer in a Group

In Kafka, a consumer group is the mechanism by which multiple consumers share reading a topic's partitions. One consumer can receive one or more partitions, yet within the same group, each partition can be assigned to at most one consumer at a time. This rule determines the parallelism a group can achieve and creates a natural upper bound when scaling the number of consumers.

Therefore, adding more consumer instances does not always increase throughput. If there are more consumers than partitions the group reads, some consumers will receive no partitions. If there are too few partitions, the group may not utilize all available processing resources; if there are many partitions yet consumers process slowly or downstream dependencies are bottlenecked, adding consumers may not resolve lag either.

This lesson belongs to the **Consumer** chapter of the **SPRING_KAFKA_MESSAGING** module, focusing on the limits of a consumer within a group, the relationship between partitions and consumers, how Spring Kafka creates concurrency, the impact of the poll loop and rebalances, and how to measure metrics to scale the system on solid evidence.

## Target outcomes

After this lesson, you will be able to:

- Explain the relationship between consumer groups, consumer members, and partitions.
- Determine the maximum number of consumers that can read a set of partitions in parallel within the same group.
- Understand why one consumer can receive multiple partitions and why excess consumers can sit idle.
- Distinguish partition-level parallelism from in-application concurrency.
- Configure listener container concurrency in Spring Kafka.
- Understand the impact of the poll loop, `max.poll.records`, `max.poll.interval.ms`, and rebalances.
- Preserve processing order when the application has multiple partitions or processes asynchronously.
- Measure consumer lag and metrics to decide whether to add consumers or add partitions.
- Design tests to verify partition assignment and practical group limits.

## 1. How does a consumer group divide partitions?

Kafka stores records in partitions. A consumer group consists of one or more consumer members sharing the same `group-id`. Members coordinate to divide reading of the partitions to which the group has subscribed.

Key rule: **a partition is assigned to at most one consumer member in the same group at any given time**. This prevents consumers in the group from concurrently reading and committing progress for the same partition in competition. A partition can still be read independently by a consumer belonging to another group.

Example topic `orders.created` with six partitions:

~~~mermaid
flowchart TB
    subgraph Topic["Topic: orders.created"]
        P0["Partition 0"]
        P1["Partition 1"]
        P2["Partition 2"]
        P3["Partition 3"]
        P4["Partition 4"]
        P5["Partition 5"]
    end
    subgraph Group["Consumer group: fulfillment"]
        C1["Consumer 1"]
        C2["Consumer 2"]
        C3["Consumer 3"]
    end
    P0 --> C1
    P1 --> C1
    P2 --> C2
    P3 --> C2
    P4 --> C3
    P5 --> C3
~~~

With three consumers and six partitions, each consumer can be assigned two partitions. One consumer does not equate to one partition: a single member can handle multiple partitions.

If the group has six consumers for six partitions, each consumer can receive one partition. If the group has eight consumers, at most six consumers receive assigned partitions; the remaining two consumers have no partitions of this topic in the current assignment.

## 2. Parallelism limit by partition count

The partition count is the upper bound on how many consumers can simultaneously receive partitions of a topic in the same group. For a topic with `P` partitions, the maximum number of useful consumers for that topic alone cannot exceed `P`.

| Partition count | Consumers in group | Consumers with partitions | Consumers without partitions |
|---:|---:|---:|---:|
| 2 | 1 | 1 | 0 |
| 2 | 2 | 2 | 0 |
| 2 | 4 | Up to 2 | At least 2 |
| 6 | 3 | Up to 3 | 0 |
| 6 | 6 | Up to 6 | 0 |
| 6 | 8 | Up to 6 | At least 2 |

The table above assumes consumers in the same group subscribe to the same topic and the topic has the stated partition count. When a group subscribes to multiple topics, consider the total partition set the group can receive under its subscription and partition assignment strategy; useful consumers remain bounded by the assigned partitions.

The ideal limit for a single topic can be expressed as:

\[
C_{active} \leq \min(C_{members}, P)
\]

Where:

- `C_active` is the number of consumers actually receiving at least one partition of the topic.
- `C_members` is the total number of consumer members in the group.
- `P` is the number of partitions of the topic.

This formula only describes the assignment bound. It does not guarantee that every consumer processes the same volume of data or achieves identical throughput. Partitions may have uneven traffic, one consumer may receive a heavier partition than another, and processing speed also depends on CPU, I/O, databases, and downstream services.

## 3. What happens when there are fewer consumers than partitions?

When there are fewer consumers than partitions, a member typically receives multiple partitions. That consumer polls data from its assigned partitions and manages offsets separately for each partition.

For example, a topic has six partitions and the group has two consumers. Each consumer may receive three partitions. This still enables parallel reading between the two consumers, yet each consumer must split its processing time across multiple partitions.

Consequences to keep in mind:

- A consumer can have multiple partitions accumulating lag even though the process itself is only one member.
- One high-traffic partition can consume most of the consumer's processing time.
- A rebalance can change the set of partitions owned by a consumer.
- If the listener processes sequentially, a single poll can return records from multiple partitions; the container dispatches them to the listener per its configured mechanism, while record ordering within each partition is preserved.

Receiving multiple partitions on one consumer does not mean Kafka merges those partitions into one log. Each partition retains its own offsets and ordering.

## 4. What happens when there are more consumers than partitions?

When a group has more consumer members than partitions, excess members receive no partition assignments. They can still join the group, send heartbeats, and wait for new assignments, yet they read no records from that topic while unassigned.

Example:

~~~mermaid
flowchart TB
    subgraph Topic["Topic: payments.authorized (3 partitions)"]
        P0["Partition 0"]
        P1["Partition 1"]
        P2["Partition 2"]
    end
    subgraph Group["Consumer group: billing"]
        C1["Consumer 1 - active"]
        C2["Consumer 2 - active"]
        C3["Consumer 3 - active"]
        C4["Consumer 4 - idle"]
        C5["Consumer 5 - idle"]
    end
    P0 --> C1
    P1 --> C2
    P2 --> C3
~~~

The two extra consumers do not make topic processing faster because they have no partitions to read. They still consume process resources, threads, connections, and can increase group management overhead.

Do not blindly deploy a consumer count equal to CPU count or a desired pod count. Align concurrency with partition count and actual traffic.

## 5. Processing order is bounded per partition

Kafka guarantees record ordering within a single partition. Kafka does not provide a global order across partitions of the same topic.

If events for the same order must be processed in sequence, producers typically use `orderId` as the key so related records are consistently routed to the same partition under the default partitioner.

Within the same consumer group:

- One partition is assigned to one member at a time.
- The consumer reads records in partition offset order.
- If the listener processes each record synchronously, the order of listener invocations within a partition preserves the order records were delivered.
- If the application offloads work to multiple threads or futures, business completion order may differ from record read order.

For example, a consumer reads `OrderCreated` then `OrderPaid` in order, yet dispatches both tasks to two separate threads. If `OrderPaid` finishes before `OrderCreated`, the order of business side effects is inverted even though Kafka delivered the records in order.

If business ordering must be preserved, process sequentially per partition or design key-partitioned processing queues. Never dump every record into an unbounded shared thread pool and assume Kafka ordering will automatically hold in downstream operations.

Increasing partition count can also affect key routing under the default partitioner. If the partition count changes, the same key may route to a different partition for new records. Therefore, partition changes must be evaluated when aggregate ordering is a strict requirement.

## 6. Partition assignment and rebalancing

The Kafka group coordinator coordinates members and partition assignments. When consumers join or leave the group, partitions are added to a topic, or subscriptions change, the group may rebalance to redistribute partitions.

Common assignment strategies include:

- **RangeAssignor:** distributes contiguous partition ranges to consumers.
- **RoundRobinAssignor:** distributes partitions cyclically across eligible members.
- **StickyAssignor:** strives to preserve existing assignments as much as possible while rebalancing.
- **CooperativeStickyAssignor:** supports cooperative assignment transfers, reducing full partition revocation during a rebalance in compatible configurations.

Actual strategy behavior depends on consumer configuration, Kafka client version, and compatibility across group members. Do not rely solely on a strategy's name to assume every distribution will be perfectly balanced.

A rebalance can create a window where some partitions pause processing while assignments change. Applications must handle offset commits and in-flight work properly. If partitions are revoked from a consumer while asynchronous work is still pending, the application may need to stop accepting new work, finish or cancel work according to policy, and avoid committing offsets past safely processed records.

Common causes of rebalances:

- Scaling application instances up or down.
- Changing listener concurrency.
- A consumer losing connectivity or failing to poll within the allowed window.
- Adding partitions to a topic.
- Changing the subscribed topic list.
- Stopping or restarting a consumer.

Rebalancing is a normal part of consumer groups. Operational goals are minimizing unnecessary rebalances and ensuring listeners recover cleanly after assignments change.

## 7. Concurrency in Spring Kafka

Spring Kafka provides concurrency for listener containers. Raising concurrency causes the container factory to create multiple consumer workers for a listener container. Each consumer has its own `KafkaConsumer`; `KafkaConsumer` is not designed for concurrent calls from multiple threads on the same instance.

Example Spring Boot configuration:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: fulfillment-service
      enable-auto-commit: false
      properties:
        "max.poll.records": 100
        "max.poll.interval.ms": 300000
    listener:
      concurrency: 3
~~~

In the configuration above, the listener container has concurrency set to three. For a listener using `group-id` `fulfillment-service`, Spring Kafka creates up to three consumer members for that container. If the application runs two identical replicas, total group members can be six, assuming both replicas host the same listener container configuration.

Illustrative listener:

~~~java
@Component
public class OrderCreatedListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "fulfillment-service"
    )
    public void consume(OrderCreatedEvent event) {
        // Business processing for one event.
    }
}
~~~

Concurrency does not create extra partitions. If a topic has two partitions and concurrency is five, at most two consumers in the container receive partitions for that topic. If a topic has six partitions and concurrency is three, each consumer can receive multiple partitions.

Concurrency can be configured per listener via `@KafkaListener` attributes or listener container factories depending on design. Ensure the resulting number of consumers is intentional, especially when multiple listeners share a group or multiple application replicas run.

## 8. The poll loop and processing time limits

Kafka consumers read data using a poll loop. On each iteration, the consumer calls poll to fetch records from assigned partitions, processes data via the listener, and polls again to maintain read progress and group membership.

Two critical properties:

- **max.poll.records:** caps the maximum number of records returned to the application in a single poll. It helps control processing batch size.
- **max.poll.interval.ms:** caps the maximum interval between poll calls. If the application does not poll again within this window, the consumer may be considered stalled and evicted from the group, triggering a rebalance.

Do not confuse `max.poll.records` with partition count or concurrency. Reducing records per poll can help the listener finish a batch faster, yet may also reduce throughput if batches become too small. Increasing `max.poll.interval.ms` may fit longer processing, yet does not replace optimizing listeners or controlling pending work.

For synchronous listeners, batch processing time must stay short enough for the container to poll on time. If per-record processing takes too long, consider:

1. Lowering `max.poll.records` to bound the number of records per poll.
2. Optimizing database queries or dependent service calls.
3. Increasing concurrency if unexploited partitions and resources remain.
4. Offloading heavy work to a bounded asynchronous processor, while carefully designing acks/offsets and rebalance handling.
5. Adjusting `max.poll.interval.ms` after measuring actual processing times and understanding the impact on group recovery.

Modern consumers have a separate heartbeat mechanism, yet that does not mean applications can ignore `max.poll.interval.ms`. The consumer must still poll within the configured window to prove active processing progress.

## 9. How can a consumer handling multiple partitions bottleneck?

Suppose one consumer receives three partitions. Partition 0 receives 100 records per second, partition 1 receives 10 records per second, and partition 2 receives 5 records per second. If the listener spends significant time per record, the high-traffic partition can drive up the consumer's total processing time and cause lag to accumulate.

Consumer lag is the difference between the latest record position and the consumer group's processed/committed progress as measured by the monitoring system. Lag should be observed per partition and over time, not just as a single aggregate number.

Signals to observe:

- Per-partition lag and total group lag.
- Topic ingress rate and processed record rate.
- Listener average, p95, and p99 processing times.
- Rebalance count and causes.
- Time between poll calls.
- Records per poll and batch processing duration.
- CPU, heap, garbage collection, and thread counts.
- Response times, connection pools, and errors on databases or downstream services.

If only one partition shows high lag, the cause may be key skew or a cluster of expensive events. If all partitions accumulate lag, total group capacity may be below the input rate or a downstream dependency may be congested.

Adding consumers only helps when unassigned partitions exist and the bottleneck lies in consumer processing capacity. If there is already one consumer per partition and lag still grows, look for another bottleneck or evaluate increasing partitions.

## 10. Consumer group scaling strategy

When throughput needs to increase, evaluate in order:

1. Measure current lag and processing rate.
2. Check partition count and active consumer members.
3. If consumers are fewer than partitions, raise concurrency or add instances to utilize idle capacity on shared partitions.
4. If consumers already equal or exceed partitions, adding consumers generally does not increase parallelism for that topic.
5. If more parallelism is required, consider increasing partitions after evaluating key ordering and broker costs.
6. Verify that databases, downstream APIs, and application resources can sustain the increased load.
7. Monitor rebalances and lag after each change.

Example topic with six partitions:

| Configuration | Maximum partition-level parallelism | Notes |
|---|---:|---|
| 1 replica, concurrency 1 | 1 | One consumer handles six partitions. |
| 1 replica, concurrency 3 | 3 | Three consumers share six partitions. |
| 2 replicas, concurrency 3 each | 6 | Six consumer members can process six partitions. |
| 3 replicas, concurrency 3 each | 6 | Nine members, yet at most six hold partitions; three members may sit idle. |

This table assumes each replica creates one listener container in the same group and all subscribe to the six-partition topic. Other members in the group or different subscriptions can alter actual assignments.

Increasing partitions is not a consequence-free operation. It can alter key distribution, consume more broker resources, shift assignments, and affect how consumers handle events for the same aggregate. Treat partition increases as an architectural change requiring planning and testing.

## 11. Limits of asynchronous processing within a single consumer

A `KafkaConsumer` is not thread-safe. Do not take one consumer and call poll, commit, or seek from arbitrary threads. Spring Kafka manages consumers on listener container threads; applications should operate through supported abstractions and acknowledgment mechanisms.

If a listener receives records and offloads work to a thread pool, the consumer can keep polling while older work has not yet finished. This increases potential parallelism, yet requires strict controls:

- Bound in-flight work so the heap does not fill up.
- Track the partition and offset of every task.
- Commit offsets only when all preceding records in that partition have completed safely.
- Handle rebalances revoking partitions while tasks are still running.
- Never let a later record commit past an earlier still-failing record.
- Ensure idempotency if records are redelivered after a consumer stops.

A simpler and more controllable approach is keeping processing synchronous inside the listener, then scaling concurrency at the container level as partitions permit. Move to asynchronous processing only when clear throughput demands justify it and acknowledgment, ordering, backpressure, and recovery mechanisms are thoroughly designed.

## 12. Testing consumer limits and partition assignments

Do not test only the number of threads created. Verify actual assignments and behavior when member counts change.

Test scenarios:

| Scenario | What to verify |
|---|---|
| 1 consumer, multiple partitions | One member can receive multiple partitions. |
| Consumers equal partitions | Partitions are distributed across members. |
| Consumers exceed partitions | Some members receive no partitions. |
| Adding a consumer at runtime | Group rebalances and redistributes partitions. |
| Stopping a consumer | Partitions are reassigned to remaining active members. |
| Increasing partitions | Assignment updates and consumers keep reading. |
| Slow listener | `max.poll.interval.ms` and rebalances behave as expected. |
| Asynchronous processing | Offsets never commit past unfinished work. |

EmbeddedKafka can be used to test listeners and assignments in simple scenarios. Testcontainers is better suited when simulating multiple brokers or configurations close to the deployment environment.

To observe assignments, use `ConsumerRebalanceListener` or Spring Kafka listener container events. Tests should wait for a specific condition with a timeout—such as all partitions being assigned—rather than relying on fixed `Thread.sleep` calls.

When testing more consumers than partitions, check the set of members with empty assignments or the number of partitions assigned to each member. Remember that exact assignments depend on the assignor, subscriptions, and when the group stabilizes.

## 13. Capstone exercise: optimizing the consumer group for orders.created

Build a topic `orders.created` with six partitions and a Spring Kafka listener belonging to group `fulfillment-service`.

Requirements:

1. Run one replica with concurrency 1 and observe one consumer receiving multiple partitions.
2. Raise concurrency to 3 and observe how partitions are redistributed.
3. Run two replicas with concurrency 3 and verify at most six members receive partitions.
4. Raise total members to nine and identify the members with no assigned partitions.
5. Send multiple records using `orderId` as key and verify events with the same key land in the same partition while partition configuration stays unchanged.
6. Simulate a slow listener to observe lag and intervals between polls.
7. Tune `max.poll.records` and measure its effect on batch processing duration.
8. Trigger a scenario exceeding `max.poll.interval.ms` in a test environment and observe the rebalance.
9. Stop one consumer and verify partitions are reassigned to remaining members.
10. Write an integration test verifying assignment and record reading after a rebalance.
11. Monitor per-partition lag to check whether key skew exists.
12. Propose concurrency and partition settings based on measured metrics.

After the exercise, record partition count, replica count, concurrency per replica, total consumer members, lag, throughput, and processing time. Do not pick concurrency solely from CPU count; choose based on partitions and measured bottlenecks.

## 14. Learning sequence and completion criteria

| Stage | Core topic | Self-check criterion |
|---|---|---|
| 1. Group model | Consumer members and partitions | Can explain why one partition belongs to at most one member in a group at a time. |
| 2. Assignment | Consumers fewer than, equal to, or exceeding partitions | Can calculate active consumers and idle members. |
| 3. Ordering | Per-partition ordering and keys | Can explain why async processing can invert completion order. |
| 4. Rebalance | Assignment strategies and group membership | Understand when partitions are revoked and reassigned. |
| 5. Spring concurrency | Listener container concurrency | Can calculate total consumer members from replicas and concurrency. |
| 6. Poll loop | `max.poll.records` and `max.poll.interval.ms` | Can diagnose slow listeners and rebalance risk. |
| 7. Scaling | Lag, throughput, and dependencies | Can decide whether to add consumers or partitions based on metrics. |
| 8. Testing | EmbeddedKafka and Testcontainers | Can test assignments, excess consumers, and rebalances. |

The lesson is complete when you can calculate a consumer group's parallelism bound from its partition count, configure concurrency in Spring Kafka, explain the impact of the poll loop and rebalances, and use consumer lag to pinpoint bottlenecks.

One consumer does not represent one partition. It can read multiple partitions, yet a partition is assigned to at most one consumer in the same group at a time. Partition count sets the ceiling for a group's parallelism; concurrency, processing time, the poll loop, and downstream capacity determine whether the group can actually exploit that limit.


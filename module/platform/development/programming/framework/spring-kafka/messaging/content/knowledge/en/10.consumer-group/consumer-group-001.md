# How Consumers Share Partitions

Kafka uses **consumer groups** to distribute the work of reading a topic across multiple consumers. Each group has its own identifier, `group.id`; consumers in the same group coordinate to receive partitions and process data in parallel. Within a group, at any given time, each partition is assigned to at most one consumer member. A consumer can receive multiple partitions, while a consumer that is not assigned any partition remains idle.

This mechanism increases processing capacity by distributing partitions across multiple consumers. The parallelism limit comes from the number of partitions: adding consumers does not create more partitions, nor does it cause a single partition to be processed concurrently by multiple members within the same group.

In Spring Kafka, `@KafkaListener` participates in this mechanism through `groupId` and consumer configuration. The `concurrency` attribute creates multiple child consumers for a listener endpoint so that Kafka distributes partitions among those consumers.

## Learning Objectives

After this lesson, you can:

- Explain how `group.id` identifies a group of consumers sharing partitions.
- Describe the relationship between the number of partitions, the number of consumers, and actual parallelism.
- Distinguish consumers in the same group from consumers in different groups.
- Explain the roles of the group coordinator and partition assignor.
- Identify the causes that trigger a rebalance and their impact on reading records.
- Configure `groupId`, `concurrency`, and the partition assignment strategy in Spring Kafka.
- Estimate throughput limits from the number of partitions and the processing capacity of each consumer.
- Inspect partition assignment, consumer lag, and group state during operations.

## 1. How Does a Consumer Group Share Work?

A topic is divided into partitions. Each partition is an ordered log of its own and can be read independently of other partitions. A consumer group allows multiple consumers to read a topic together, while each partition is assigned to at most one member in the group at the same time.

For example, the `orders` topic has four partitions and the `order-service` group has two consumers:

~~~text
Topic orders
+---------+---------+---------+---------+
|    P0   |    P1   |    P2   |    P3   |
+---------+---------+---------+---------+
     |         |         |         |
     +----+----+         +----+----+
          |                   |
          v                   v
     Consumer A          Consumer B
     P0, P1               P2, P3

Consumer group: order-service
~~~

Consumer A reads partitions 0 and 1; Consumer B reads partitions 2 and 3. Both belong to the same group, so they coordinate to share the work. If Consumer A stops, Kafka can trigger a rebalance so that A's partitions are assigned to the remaining member.

Core principles:

- A partition is not assigned simultaneously to two members within the same consumer group.
- A single consumer can be assigned multiple partitions.
- Consumers in the same group share a single data stream; during a stable assignment, one member reads that partition. Records can still be redelivered if processing is not yet complete or the offset has not yet been committed.
- Each consumer group has its own offsets for each partition.
- Different partitions do not have a global order across one another.

The statement "a partition has only one consumer" must be understood with the right scope: that is one consumer member within one group at a time. A topic can still be read independently by multiple different groups.

## 2. The Number of Partitions Limits the Number of Active Consumers

For a topic with `P` partitions and a consumer group with `C` consumer members, the number of consumers that can receive at least one partition is at most `min(P, C)`.

For example, a topic with six partitions:

| Partitions | Consumers in group | Possible outcome |
|---:|---:|---|
| 6 | 1 | One consumer reads all six partitions |
| 6 | 2 | Two consumers, about three partitions each |
| 6 | 3 | Three consumers, about two partitions each |
| 6 | 6 | Six consumers, one partition each |
| 6 | 8 | At most six consumers have partitions; the remaining two consumers are idle |

Diagram when there are more consumers than partitions:

~~~text
Topic orders: P0  P1  P2  P3

Consumer A:   P0
Consumer B:   P1
Consumer C:   P2
Consumer D:   P3
Consumer E:   (no partition)
Consumer F:   (no partition)
~~~

Consumers E and F can still be members of the group, but they have no data from this topic to read. Increasing the number of consumers from four to six does not increase the parallelism of a four-partition topic.

Conversely, if there are fewer consumers than partitions, each consumer receives multiple partitions. This still allows parallel reading across partitions, but partitions assigned to the same consumer share the same consumer thread when the listener processes synchronously.

**Important limitation:** a topic with only one partition can have only one consumer member in a group receiving that partition. If you need to increase parallel processing capacity for a topic, you must design the partition count upfront based on load and business ordering requirements.

## 3. Different Consumer Groups Receive Data Independently

Two consumers in the same group share partitions. Two consumers in two different groups can read the entire topic independently of each other.

For example, the `orders` topic has three partitions and two groups:

~~~text
                         Topic orders
                    +------+------+------+
                    |  P0  |  P1  |  P2  |
                    +------+------+------+
                       |      |      |
             +---------+------+------+
             |                        |
             v                        v
      Group: billing             Group: analytics
      Consumer B1                Consumer A1
      Consumer B2                Consumer A2
      Consumer B3                Consumer A3

      Each group has its own assignment for all of P0, P1, P2.
~~~

The `billing` group can process events to update payments; the `analytics` group can read the same events to aggregate reports. When one group commits its offsets, it does not change the offsets of the other group.

Offsets are stored per group and partition. Therefore, the same record can be read by each group at different times, or replayed by one group without affecting the progress of the remaining group.

This is the foundation of the publish-subscribe model:

- A producer sends a record to a topic.
- Each consumer group is an independent consumption stream.
- Members within a group share partitions.
- Different groups receive data independently according to their own offsets.

Do not create a new consumer group for each consumer if the goal is to share load among them. If each consumer has a different `group.id`, each consumer will read the entire dataset according to its own progress, increasing processing counts and broker load.

## 4. Group Coordinator and Partition Assignor

When a consumer uses `subscribe()`, it joins a consumer group. A broker is elected as the **group coordinator** to manage membership, heartbeats, generations, and the assignment synchronization process.

The partition assignor decides how to distribute the topic's partitions to the members in the group. The coordinator coordinates with the members to complete the assignment according to the group protocol.

High-level group join flow:

~~~mermaid
sequenceDiagram
    participant A as Consumer A / Group Leader
    participant B as Consumer B
    participant G as Group Coordinator
    A->>G: JoinGroup
    B->>G: JoinGroup
    G-->>A: Select A as group leader (classic protocol)
    A->>A: Assignor computes partition assignment
    A->>G: Send member assignments
    G-->>A: Assignment for A
    G-->>B: Assignment for B
    A->>G: Heartbeat
    B->>G: Heartbeat
~~~

In the classic consumer group protocol, the group coordinator manages membership and selects a group leader; the assignor runs on the group leader to compute the assignment and then sends the result back to the coordinator. The coordinator distributes the assignment to the members. With the new consumer group protocol, the broker can take over computing assignments via a server-side assignor. The coordinator tracks members through heartbeats and consumer progress milestones. When membership or subscriptions change, the group may need to recompute the assignment.

The partition assignor can use different strategies:

| Strategy | High-level distribution method | Characteristics |
|---|---|---|
| RangeAssignor | Assigns contiguous partition ranges to consumers per topic | Easy to understand; can create uneven distribution across consumers with multiple topics |
| RoundRobinAssignor | Distributes partitions in round-robin order across eligible consumers | Can distribute more evenly across multiple topics if subscriptions are compatible |
| StickyAssignor | Tries to balance while preserving existing assignments as much as possible | Reduces the number of partitions that must move when the group changes |
| CooperativeStickyAssignor | Sticky assignment with a cooperative/incremental rebalance mechanism | Can revoke and reassign partitions incrementally, reducing stop-the-world pauses across the group |

Available strategies and default behavior depend on the Kafka client version, broker version, and group protocol. Check the actual configuration rather than assuming every cluster uses the same assignor.

### Configuring the Partition Assignment Strategy

In the classic consumer group protocol, the client can configure `partition.assignment.strategy`. For example, selecting the cooperative sticky assignor:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        "[partition.assignment.strategy]": org.apache.kafka.clients.consumer.CooperativeStickyAssignor
~~~

All consumer members in the same group must have compatible configurations. When changing the assignor in a running environment, deploy according to the compatibility guidelines of your Kafka client and broker versions; uncoordinated changes can prevent the group from agreeing on an assignment strategy.

Kafka versions that support the new consumer group protocol can move part of assignor selection to the broker. When using that protocol, configuration methods and related properties may differ from the classic protocol. Check the documentation for the exact Kafka version you are using.

## 5. Rebalance: Reassigning Partitions When the Group Changes

A **rebalance** is the process by which a consumer group computes and redistributes partitions among its members. Rebalancing is necessary for the group to continue operating when the number of consumers or the set of partitions changes.

Common triggers:

- A new consumer joins the group.
- A consumer stops gracefully or crashes.
- A consumer fails to send a heartbeat within the allowed session timeout.
- A consumer fails to call `poll()` again within `max.poll.interval.ms`.
- A member's subscription changes.
- Partitions are added to a topic, or a topic pattern discovers a new topic.
- Certain configuration changes or group states require a new assignment.

For example, initially there are two consumers:

~~~text
Before rebalance:
P0  P1  P2  P3  P4  P5
|   |   |   |   |   |
+---+---+---+   +---+---+
        |           |
    Consumer A  Consumer B
      P0-P3       P4-P5
~~~

When Consumer C joins, the group can redistribute:

~~~text
After rebalance:
P0  P1  P2  P3  P4  P5
|   |   |   |   |   |
+---+   +---+   +---+
  |       |       |
Consumer A Consumer B Consumer C
  P0-P1     P2-P3     P4-P5
~~~

The diagram only illustrates a balanced outcome; the actual assignment depends on the assignor and membership.

During a rebalance, partitions may be revoked from the old consumer and handed to a new consumer. Listeners may pause receiving additional records. If a record has been processed but its offset has not been committed, the record may be redelivered after the rebalance. Therefore, consumers should process idempotently.

### Eager and Cooperative Rebalance

With an eager rebalance, the group can revoke all currently assigned partitions before redistributing them. This causes wider processing disruption during the rebalance.

Cooperative rebalance allows partitions to be revoked and transferred incrementally. It can reduce the scope of disruption because partitions that do not need to change owners can continue to be processed. However, it does not eliminate all rebalances or all possibilities of duplicate processing.

Choosing an appropriate assignor and keeping listener processing times within limits are two key factors in reducing unnecessary rebalances.

## 6. Configuring a Consumer Group in Spring Boot

A consumer needs a `group-id` to join a group and store offsets per group. Spring Boot can configure the group ID and listener properties:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-service
      enable-auto-commit: false
      auto-offset-reset: earliest
    listener:
      concurrency: 3
~~~

In the example:

- `group-id: order-service` sets the group name for the consumer.
- `enable-auto-commit: false` lets the Spring Kafka listener container manage offset commits according to the acknowledgement mode.
- `auto-offset-reset: earliest` specifies the starting position when the group does not yet have a valid committed offset or the offset is out of the log range.
- `concurrency: 3` instructs the listener container to create up to three child consumers for the default endpoint.

`auto-offset-reset` does not mean the consumer re-reads from the beginning every time the application starts. If the group already has a valid committed offset, the consumer continues from the saved position.

In an application with multiple listeners, you can set `concurrency` individually for each endpoint or create separate container factories. Verify which factory a listener actually uses to avoid configuring one factory while the endpoint uses another.

## 7. Dividing Partitions with @KafkaListener Concurrency

Example listener processing order events:

~~~java
@Component
public class OrderListener {

    @KafkaListener(
        id = "order-listener",
        topics = "orders",
        groupId = "order-service",
        concurrency = "3"
    )
    public void handle(OrderEvent event) {
        orderService.processIdempotently(event);
    }
}
~~~

With a six-partition topic, a concurrency of three creates three child consumers in the same group. The group coordinator and assignor distribute the partitions across those three consumers.

An equivalent configuration is setting concurrency on the container factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    return factory;
}
~~~

The listener references the factory:

~~~java
@KafkaListener(
    id = "order-listener",
    topics = "orders",
    groupId = "order-service",
    containerFactory = "orderListenerContainerFactory"
)
public void handle(OrderEvent event) {
    orderService.processIdempotently(event);
}
~~~

There is no need to set conflicting concurrency values in multiple places at the same time. Choose the configuration location that fits how your application's listeners are organized.

### Relationship Between Concurrency and Partitions

For an endpoint processing a single topic:

- If the partition count is greater than `concurrency`, a child consumer may receive multiple partitions.
- If the partition count equals `concurrency`, each child consumer can receive one partition.
- If the partition count is less than `concurrency`, some child consumers receive no partitions.
- When `concurrency` changes, the group may rebalance to redistribute assignments.

Concurrency only creates more consumers within the application. It does not increase the number of partitions and does not guarantee linear throughput scaling. If downstream systems such as a database or HTTP service are already saturated, adding consumers may only increase concurrent requests and pressure on the dependency.

## 8. Consumer Groups and Processing Order

Kafka guarantees record order within each partition by offset. When a consumer receives multiple partitions, it can read those partitions within the same poll loop, but there is no global order across them.

For example, events for the same order use `orderId` as the key:

~~~java
kafkaTemplate.send("orders", orderId, event);
~~~

Records with the same key are usually routed to the same partition with the default partitioner as long as the partition count and routing configuration do not change. Therefore, the consumer handling that partition can read the events in offset order.

When there are multiple consumers in the same group:

- Each partition is still assigned to only one consumer member at a time.
- Different partitions can be processed in parallel.
- Records from the same partition are delivered in offset order.
- If the listener hands work off to an executor or processes asynchronously, the completion order of side effects may differ from the order in which records were received.
- A rebalance can move a partition to another consumer; the application must tolerate redelivered records.

If business logic requires ordering per entity, choose an appropriate key and avoid processing records from the same partition in parallel in ways that invert update order.

## 9. Static Membership and Reducing Rebalances on Restart

Kafka supports static membership via `group.instance.id` in the classic consumer group protocol. A member with a stable instance identifier can retain its membership across brief restarts instead of immediately being treated as a new member.

Example property:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        "[group.instance.id]": order-worker-1
~~~

The `group.instance.id` value must be unique across active instances in the same group. Do not use the same value for multiple application replicas because the coordinator can detect duplicate members and fence one of them.

Static membership can reduce rebalances during rolling restarts, but with a trade-off: partitions may continue to be held by a temporarily disconnected member until the session expires. Choose a session timeout appropriate for your restart duration and failover goals.

In Spring Kafka, if multiple child consumers are created from a concurrent container, ensure each consumer has a suitable, unique instance identifier according to the requirements of your Kafka client/version. Do not copy a single fixed `group.instance.id` to all child consumers.

## 10. Consumer Groups When Scaling Applications

Suppose the `order-service` application has six partitions and three replicas. Each replica is configured with `concurrency` of two, totaling up to six consumer members in the group:

~~~text
Kubernetes / Application replicas
  order-service-1: consumer 1, consumer 2
  order-service-2: consumer 3, consumer 4
  order-service-3: consumer 5, consumer 6

Consumer group: order-service
Topic: orders (6 partitions)
~~~

When scaling from three to four replicas while keeping `concurrency` at two, the group has eight consumer members, but the topic only has six partitions. At most six consumers receive partitions; the remaining two consumers stay idle.

When scaling down, consumers leave the group and partitions are redistributed to the remaining members. If an application stops abruptly, the coordinator must detect the lost member via heartbeat/session or poll progress mechanisms before the rebalance completes.

Operational notes:

- Total consumer members equal the number of replicas multiplied by the concurrency per replica if all replicas run the same endpoint.
- Useful consumers are capped by the total number of partitions the group subscribes to.
- Scaling beyond the partition count does not increase topic parallelism.
- Scaling down can increase the number of partitions per consumer and the processing load per thread.
- Rebalancing creates a brief pause and can increase redelivered records.
- When changing the partition count, the assignor can redistribute partitions and change which consumers own them.

## 11. Monitoring Consumer Groups with Kafka CLI

You can use the Kafka CLI to inspect groups, members, and partition assignments.

List groups:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list
~~~

View group offsets and lag:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-service
~~~

View members and partition assignments on supported CLI versions:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-service \
  --members \
  --verbose
~~~

The describe output usually helps determine:

- How many members the consumer group has.
- Which member is assigned which partitions.
- The group's current offset.
- The log end offset and consumer lag.
- Which partitions currently have no consumer processing them.

Syntax and displayed fields may vary across Kafka versions. Use the scripts bundled with the matching broker/client version.

## 12. Observability in Spring Kafka

In a Spring Kafka application, you should monitor both listener container state and consumer group state together:

- Consumer lag by group and partition.
- Number of active consumer members.
- Partition assignment of each listener container.
- Rebalance count and completion duration.
- Listener processing time and error rate.
- Counts of retried, dead-letter, and duplicate records.
- Time from receiving a record to committing its offset.

Increasing lag in a group does not necessarily mean there are too few consumers. Causes can include slow listener processing, an overloaded database, a hot partition, continuous rebalancing, or failing records being retried repeatedly.

Compare lag per partition. If only one partition's lag grows while other partitions remain stable, that partition may be receiving most of the traffic or contain a hot key. Increasing concurrency will not spread a single hot partition across multiple consumers in the same group.

## 13. Common Design Mistakes

**Creating many consumers with the same group ID when the topic has few partitions.** Excess consumers will not be assigned any partitions. Check the partition count before increasing replicas or concurrency.

**Giving each consumer a different group ID when load sharing was intended.** Each group independently reads the entire topic; data will be processed redundantly across groups. Share the same group ID for members that should divide the work.

**Assuming a consumer group guarantees global topic ordering.** Kafka only guarantees ordering within each partition. Use keys to route events that require ordering into the same partition.

**Increasing concurrency without measuring downstream capacity.** More consumers can overload databases or APIs. Measure processing time, lag, and throughput before scaling up.

**Listener taking too long so the consumer cannot poll in time.** This can exceed `max.poll.interval.ms` and trigger rebalances. Optimize the listener, and tune `max.poll.records` and timeouts to match actual processing times.

**Not making handlers idempotent.** Rebalances, restarts, or errors before commit can cause records to be redelivered. Use event IDs, unique constraints, or the inbox pattern to avoid duplicate side effects.

**Using the same static member ID across multiple instances.** Members can be fenced or the group can continuously churn. Each instance requires a unique identifier if static membership is used.

## 14. Testing How a Group Divides Partitions

Integration tests should run Kafka with enough partitions and multiple consumer members. Useful scenarios:

- Create a six-partition topic and start three consumers in the same group; verify the group assignment covers all six partitions.
- Increase consumers to eight; verify that at most six consumers receive partitions from this topic.
- Start two different groups; verify each group independently reads the same records.
- Stop one consumer; verify partitions are redistributed to the remaining members.
- Start a new consumer; verify the rebalance and resulting assignment.
- Increase the partition count; verify the group updates its assignment after rebalancing.
- Send multiple records with the same key; verify they land in the same partition and the listener processes them in offset order.
- Make a listener slow or throw an exception; observe poll interval, retry, and rebalance behavior.
- Scale the application up/down; measure lag and recovery time.

In tests, wait for the assignment to complete before sending or asserting on records. Do not use a short fixed sleep and assume the group has stabilized; use assignment state or synchronization conditions with explicit timeouts.

## 15. Consumer Group Design Checklist

- [ ] Consumers that need to share load have the same `group.id`.
- [ ] Applications that need independent reads use separate group IDs.
- [ ] The partition count is sufficient for the desired parallelism.
- [ ] Total consumer members account for both application replicas and concurrency.
- [ ] The partition assignor matches balancing and partition-movement-reduction needs.
- [ ] Rebalances, restarts, and consumer failures have been tested.
- [ ] Listeners are idempotent to tolerate redelivered records.
- [ ] Keys ensure events requiring ordering land in the same partition.
- [ ] `max.poll.interval.ms` and `max.poll.records` align with processing times.
- [ ] Dashboards/metrics exist for assignment, lag, rebalances, and errors.
- [ ] Static membership is enabled only with unique identifiers and a clear failover plan.

## Conclusion

A consumer group shares partitions by assigning each partition to at most one consumer member in the same group at a time. A single consumer can receive multiple partitions; if the number of consumers exceeds the number of partitions, the extra consumers stay idle. Different groups read the topic independently with their own offsets. In Spring Kafka, `groupId` identifies the group and `concurrency` controls the number of child consumers for a listener. Design the partition count according to required parallelism, choose an appropriate assignor, handle rebalances, and make listeners idempotent so the group remains stable during scaling or failures.


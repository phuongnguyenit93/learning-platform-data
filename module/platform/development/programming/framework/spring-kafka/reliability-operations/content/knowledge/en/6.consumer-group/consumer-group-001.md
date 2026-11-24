# Partition Assignment and Ownership

In a Kafka consumer group, partition assignment determines which consumer member is responsible for reading each partition of a topic. Ownership is the state in which a consumer member is granted the authority to process a partition within the group at a given point in time. These two concepts determine how Kafka distributes load, maintains ordering within a partition, recovers when a consumer leaves the group, and handles application scaling.

In Spring Kafka, each Kafka listener container manages one or more `KafkaConsumer` instances. When a listener uses standard group management, consumers join a group using the same group ID, and Kafka distributes partitions among the members. Spring Kafka manages the consumer lifecycle, listener threads, offset commits, and rebalance callbacks; the distribution algorithm still belongs to Kafka's consumer group mechanism.

It is important to distinguish three concepts:

- **Partition leader**: the broker acting as the leader for a partition on the cluster. The leader broker handles read and write requests for the partition.
- **Consumer group coordinator**: the broker that coordinates group membership and rebalances.
- **Partition owner**: the consumer member assigned to process a partition within a consumer group.

A partition can have multiple consumer groups reading independently. However, within the same group, at a stable point in time, a partition is assigned to at most one consumer member. This is the basis for consumers in a group to share load without intentionally processing the same partition concurrently.

## 1. Consumer Group and Partition Ownership

A consumer group is a set of consumers sharing the same group ID. Each member joins the group by registering a subscription for one or more topics. Kafka uses the membership and subscription information to generate an assignment.

For example, suppose topic `orders` has six partitions and the `orders-service` group has three consumer members:

~~~text
Topic orders:  P0  P1 | P2  P3 | P4  P5
Owner:          A   A |  B   B |  C   C

Consumer group: orders-service
~~~

The diagram only illustrates one possible assignment. The actual assignor algorithm and subscriptions determine which partition belongs to which member.

If a group has fewer consumers than partitions, a consumer may own multiple partitions. If a group has more consumers than subscribed partitions, some consumers will not be assigned any partitions and will not receive records from those partitions. Increasing the number of consumers beyond the number of partitions does not increase parallel reading capacity for that topic.

Ownership is defined within the scope of a group:

- Consumer A in group `orders-service` can own partition P0.
- Consumer X in group `fraud-service` can also read P0.
- Two consumers belonging to different groups have independent offsets and progress.
- Within the same `orders-service` group, P0 is not assigned to both Consumer A and Consumer B in a stable assignment.

Therefore, creating a new group ID usually means creating an independent reading stream, not adding another worker to the same processing group.

## 2. Who Decides Partition Assignment?

In the traditional consumer group protocol (classic group protocol), the process involves the following roles:

1. A consumer connects to Kafka and sends a request to join the group with its group ID, member identity, and subscription.
2. The group coordinator manages membership, generations, and rebalance state.
3. Members exchange metadata regarding their subscriptions and assignor capabilities.
4. One member is elected as the group leader in the classic protocol; this member runs the partition assignor to compute the assignment for the entire group.
5. The assignment is sent back through the coordinator so that members receive their respective partitions.
6. Each consumer starts fetching from its assigned partitions and continues maintaining its membership.

The group leader in this process is a consumer member tasked with computing the assignment. It is not the broker leader of a topic partition. The group coordinator is the broker coordinating the group; it is also not a consumer processing records.

Kafka has different generations of the consumer group protocol. With the classic protocol, the model where a client-side group leader runs the assignor is the common explanation. Newer Kafka versions have also introduced a new consumer group protocol, in which some assignment responsibilities are moved to the broker side. Implementation details depend on the broker and client versions, but the principle of ownership within a group remains the same.

Important information when joining a group includes:

- **group.id**: the group identifier. Consumers that want to share load and share commit progress must join with the same group ID.
- **Subscription**: the set of topics a consumer wants to read, or a pattern-based subscription.
- **Partition assignor**: the algorithm that decides how partitions are distributed among members.
- **Member identity**: the identifier of a consumer member in the group.
- **Generation**: the version of the group's membership/assignment. When a rebalance completes, a new generation represents the new membership.

## 3. Lifecycle of an Assignment

Partition assignment is not an immutable configuration. It can change when a consumer joins or leaves the group, misses heartbeats, changes its subscription, or when topic metadata changes.

A typical lifecycle:

~~~text
Consumer starts
       |
       v
Subscribe to topic / join group
       |
       v
Coordinator records membership
       |
       v
Rebalance and compute assignment
       |
       v
Consumer receives assigned partitions
       |
       v
Poll records and process
       |
       +------ membership changed? ---------+
       |                                   |
       | No                                | Yes
       v                                   v
Continue processing                  Revoke / release
                                           |
                                           v
                                  New assignment
                                           |
                                           v
                                  Consumer owns
                                  new partitions
~~~

A rebalance can occur in the following situations:

- A new consumer starts up and joins the group.
- A consumer shuts down or closes.
- A consumer crashes or loses connectivity.
- A consumer fails to send heartbeats within the allowed limit.
- A consumer fails to call `poll` in time and exceeds `max.poll.interval.ms`.
- Topic subscriptions or patterns change.
- A topic gets additional partitions or metadata changes the partition set.
- Group members change due to deployments, autoscaling, or infrastructure incidents.

When an assignment changes, some partitions may be revoked from an old member and assigned to a new member. The consumer needs to stop accepting new work on the revoked partitions and safely complete or cancel in-flight work before relinquishing ownership. Kafka manages read authority within the group, but it cannot automatically fence a side effect already running against a database or an external system outside Kafka; the application must handle that case using idempotency or its own fencing mechanism. This is also the time to commit offsets according to policy if the consumer still holds valid authority to do so.

## 4. Eager Rebalance and Cooperative Rebalance

A rebalance can revoke partitions in two general ways: eager and cooperative.

### Eager rebalance

With an eager assignment protocol, when the group needs to rebalance, members revoke all partitions they currently own. After the group computes the new assignment, each member receives its corresponding set of partitions.

~~~text
Before rebalance:
  Consumer A: P0, P1
  Consumer B: P2, P3

Eager revoke:
  Consumer A: (holds no partitions)
  Consumer B: (holds no partitions)

After rebalance:
  Consumer A: P0, P2
  Consumer B: P1, P3
~~~

During the rebalance window, revoked partitions may temporarily not be processed by any consumer. When a group is large or has many partitions, this pause can increase consumer lag.

### Cooperative rebalance

Cooperative rebalance allows partitions to be transferred incrementally. Only partitions that need to change owners are revoked; partitions that remain with their old member can continue to be retained. After one or more rebalance rounds, the group reaches the new assignment.

~~~text
Before:
  Consumer A: P0, P1
  Consumer B: P2, P3

New target:
  Consumer A: P0, P2
  Consumer B: P1, P3

Cooperative round:
  A revokes P1
  B revokes P2
  P0 and P3 remain with old owner

Assignment complete:
  Consumer A: P0, P2
  Consumer B: P1, P3
~~~

The cooperative protocol reduces the number of partitions that must stop and move in a single rebalance. It generally helps reduce disruption when a group has many members or many partitions. However, the application still needs to handle revoke callbacks and partition ownership transfers; cooperative does not mean there are no more rebalances.

Kafka provides assignors that support the cooperative protocol, such as `CooperativeStickyAssignor`. When configuring multiple assignors for a rolling upgrade, follow the compatibility guidelines for your Kafka client version; do not arbitrarily mix eager and cooperative assignors in an invalid configuration.

## 5. Common Partition Assignors

An assignor takes the set of partitions to distribute and the set of eligible consumer members, then produces a member-to-partitions mapping. Each strategy optimizes for a different goal.

### RangeAssignor

`RangeAssignor` distributes partitions on a per-topic basis. For each topic, partitions are ordered and divided into contiguous ranges for the consumer members subscribed to that topic.

For example, topic `orders` has five partitions and two consumers:

~~~text
orders: P0 P1 P2 P3 P4

Consumer A: P0 P1 P2
Consumer B: P3 P4
~~~

When the number of partitions is not evenly divisible by the number of consumers, some consumers receive one extra partition. With multiple topics, the division is performed separately per topic, so the total number of partitions across consumers can become significantly skewed if subscriptions differ or partition counts vary across topics.

Range can be suitable when you want contiguous partitions to belong to the same consumer, though it does not always produce the most balanced overall distribution.

### RoundRobinAssignor

`RoundRobinAssignor` sorts the partitions and distributes them in turn across eligible consumers in a round-robin fashion.

For example:

~~~text
Partition: P0 P1 P2 P3 P4 P5
Consumer:   A  B  C  A  B  C

Consumer A: P0, P3
Consumer B: P1, P4
Consumer C: P2, P5
~~~

Round robin generally produces a more even distribution across the total set of partitions when consumers have similar subscriptions. If consumers subscribe to different sets of topics, only eligible members receive the corresponding partitions, and the result may not divide evenly.

### StickyAssignor

`StickyAssignor` aims for two goals: balancing the number of partitions and preserving existing assignments as much as possible. When membership changes, it tries to move only the partitions necessary to reach a new balanced assignment.

Keeping assignments stable helps reduce the cost of reinitializing processing, local caches, state, and resource connections tied to partitions. `StickyAssignor` uses the eager rebalance protocol.

### CooperativeStickyAssignor

`CooperativeStickyAssignor` combines the balancing and minimal-movement goals of sticky assignment with the cooperative rebalance protocol. Partitions that do not need to change owners can continue to be processed while those that must move are revoked incrementally.

This is a commonly considered choice for groups with many partitions or when minimizing disruption during scaling is needed. Availability and defaults depend on the Kafka client, broker, and group protocol versions in use.

### Quick comparison

| Assignor | Primary goal | Behavior when membership changes |
|---|---|---|
| RangeAssignor | Divide contiguous partition ranges per topic | May cause significant partition movement and eager rebalances |
| RoundRobinAssignor | Distribute sequentially across the partition set | Can balance overall load, but assignments may shift when members change |
| StickyAssignor | Balance load and preserve previous assignments | Minimizes partition movement, uses eager protocol |
| CooperativeStickyAssignor | Balance, preserve previous assignments, and migrate incrementally | Only revokes partitions that need to move via cooperative protocol |

There is no single best assignor for every system. The choice depends on the number of topics, partition count, per-member subscriptions, state migration cost, balance requirements, and acceptable disruption levels.

## 6. Configuring Partition Assignment in Spring Kafka

Spring Boot forwards producer and consumer properties to the Kafka client. Since the assignor is a consumer property, it can be declared in the consumer configuration:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-service
      properties:
        "[partition.assignment.strategy]": org.apache.kafka.clients.consumer.CooperativeStickyAssignor
~~~

The class name must exist in the Kafka client version being used. If using multiple assignors for a rolling transition, configure the list in the format required by the Kafka client and verify compatibility across members.

It can also be configured in Java:

~~~java
Map<String, Object> consumerProps = new HashMap<>();
consumerProps.put(
        ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "localhost:9092");
consumerProps.put(
        ConsumerConfig.GROUP_ID_CONFIG,
        "orders-service");
consumerProps.put(
        ConsumerConfig.PARTITION_ASSIGNMENT_STRATEGY_CONFIG,
        CooperativeStickyAssignor.class.getName());
~~~

This is the configuration for a Kafka consumer factory. In a real Spring Boot application, you also need to configure deserializers, security, offset reset, and other relevant properties.

You should not simply change the assignor and expect the entire group to automatically switch to cooperative mode in every case. All members joining the group must have compatible configurations and versions. When performing a rolling upgrade, follow Kafka's migration procedure for the assignor and protocol in use.

## 7. Ownership in Spring Kafka Listener Containers

Spring Kafka creates consumers and coordinates them through listener containers. With `ConcurrentMessageListenerContainer`, the `concurrency` property creates multiple child `KafkaMessageListenerContainer` instances; each child manages its own `KafkaConsumer`.

For example:

~~~java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            kafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        return factory;
    }
}
~~~

A listener using the factory above:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "orders-service",
        containerFactory = "kafkaListenerContainerFactory")
public void handle(OrderEvent event) {
    process(event);
}
~~~

With the configuration above, the container creates three consumer members in the `orders-service` group. If the topic has at least three partitions and all members subscribe to the same topic, each member can receive one or more partitions depending on the assignment. If the topic only has two partitions, one of the three consumers will not be assigned any partition.

Concurrency is the number of consumer threads managed by the container, not the number of partitions, and it does not guarantee each thread always receives exactly one partition. Actual assignment also depends on:

- The number of partitions in the topic.
- The number of child consumers in the container.
- The number of application instances running with the same group ID.
- The subscription of each listener/member.
- The partition assignor.

If an application runs three replicas and each replica has a concurrency of 3, the group may have a total of nine consumer members for that listener. With a topic that only has six partitions, at least three members will not be assigned any partitions in a stable assignment. Increasing concurrency beyond the partition count increases threads and resource usage without increasing parallel reading capacity.

### Multiple topics and multiple listeners

When a consumer subscribes to multiple topics, the assignor evaluates each member's subscription. If different listeners subscribe to different sets of topics while sharing the same group ID, understand that Kafka distributes partitions based on each member's valid subscription. Do not arbitrarily share a group ID across listeners with independent business purposes, as they may compete for assignments or produce unexpected distributions.

Typically, consumers processing the same business stream with the same schema/logic should share a group ID to split the load. Applications that need to receive all events independently should use separate group IDs.

## 8. Callbacks When Partitions Are Revoked or Assigned

When a rebalance occurs, the application may need to finish in-flight work, save local state, or record ownership changes. The Kafka Consumer API provides `ConsumerRebalanceListener` with the following callbacks:

- `onPartitionsRevoked`: partitions are about to be revoked in an eager rebalance or transferred away in a cooperative rebalance.
- `onPartitionsAssigned`: new partitions are assigned to the consumer.
- `onPartitionsLost`: partitions have already lost ownership, typically because the consumer is no longer a valid member or the group has moved on; do not assume there is enough time left to commit.

Example using the Kafka Consumer API:

~~~java
consumer.subscribe(
        List.of("orders"),
        new ConsumerRebalanceListener() {
            @Override
            public void onPartitionsRevoked(
                    Collection<TopicPartition> partitions) {
                flushPartitionState(partitions);
                commitOffsetsFor(partitions);
            }

            @Override
            public void onPartitionsAssigned(
                    Collection<TopicPartition> partitions) {
                initializePartitionState(partitions);
            }

            @Override
            public void onPartitionsLost(
                    Collection<TopicPartition> partitions) {
                discardOwnershipState(partitions);
            }
        });
~~~

The snippet illustrates the Kafka consumer API. In Spring Kafka, you can register a `ConsumerRebalanceListener` through container properties or container configuration appropriate for your Spring Kafka version. Check the exact API signature for your project's version.

The revoke callback should finish quickly. If the callback performs database calls or flushes state for too long, the rebalance can drag out and cause consumer lag to rise. Do not call synchronous commits arbitrarily inside the callback; understand your ack mode, commit strategy, and group timeouts.

With cooperative rebalance, the revoke callback only receives the partitions actually being revoked in the current round. Do not assume all partitions will always be revoked. The assign callback may also be invoked across multiple rounds for the group to complete the assignment.

## 9. Partition Ownership and Offset Are Two Different States

Ownership determines which consumer is permitted to read and process a partition in the group. Offset represents the reading progress position and the committed position for the group to recover after a restart or rebalance. The two concepts are related but not identical.

For example:

- Consumer A owns partition P0.
- Consumer A has read up to offset 120.
- The most recently committed offset is 115.
- Consumer A loses membership and P0 is assigned to Consumer B.
- Consumer B resumes from the committed offset according to the relevant isolation and reset policies, potentially re-reading records starting from offset 116.

Consumer B re-reading some records is normal at-least-once behavior when offsets have not been committed after processing. New ownership does not automatically prove that prior records were processed successfully.

In Spring Kafka, the ack mode determines when the container commits offsets:

| Ack mode | General meaning |
|---|---|
| RECORD | Commit offset after the listener finishes processing each record, according to container mechanics |
| BATCH | Commit after processing the batch of records from a poll |
| TIME | Commit on a time interval when processed records exist |
| COUNT | Commit when a configured number of processed records is reached |
| COUNT_TIME | Combines count and time thresholds |
| MANUAL | Listener confirms via `Acknowledgment`; container commits according to manual rules |
| MANUAL_IMMEDIATE | Commit immediately upon acknowledgment depending on calling thread conditions and container config |

Exact names and behavioral details should be verified against your Spring Kafka version. Regardless of the chosen ack mode, the application must understand the gap between processed records and committed offsets. If a consumer loses ownership before committing, records may be redelivered to a new member.

Do not continue processing or committing offsets for a partition after the consumer has lost ownership. If an asynchronous task continues running after the listener returns, design it so the task does not cause duplicate side effects when the partition is assigned to another consumer.

## 10. Manual Assignment and Group-Managed Assignment

Kafka supports two ways to receive partitions:

### Subscribe and group management

With `subscribe()`, the consumer joins a group and Kafka manages membership, rebalances, and assignments.

~~~java
consumer.subscribe(List.of("orders"));
~~~

This is the standard approach when multiple Spring Kafka instances need to share load and recover automatically when members change.

### Manual partition assignment

With `assign()`, the application directly specifies the `TopicPartition`s that the consumer will read:

~~~java
consumer.assign(List.of(
        new TopicPartition("orders", 0),
        new TopicPartition("orders", 1)));
~~~

Manual assignment does not participate in group-managed assignment and automatic rebalancing like `subscribe()`. The application is responsible for deciding which member reads which partition and handling ownership transitions when instances change. You cannot call `subscribe()` and `assign()` simultaneously on the same consumer.

In Spring Kafka, a listener can use the `topicPartitions` attribute to specify concrete partitions. This is suitable for certain fixed workloads or when the application needs explicit assignment control. However, you must design the partition distribution across instances yourself and avoid configuring two instances to read the same partition unless duplicate processing is intended.

Manual assignment is not a default solution for increasing performance. It removes the group's automatic coordination mechanism, so in exchange the application assumes responsibility for operations and recovery.

## 11. Static Membership and Reducing Unnecessary Rebalances

Every time a consumer member leaves a group and rejoins, the group may need to rebalance. For applications that restart frequently due to rolling deployments or maintenance, continuous membership changes can trigger frequent rebalances.

Static membership allows a consumer to declare a stable `group.instance.id`. When a consumer temporarily disconnects within the session timeout limit, the coordinator can hold the member's slot instead of immediately treating it as a new member. This helps reduce unnecessary rebalances during certain short restart scenarios.

For example:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-service
      properties:
        "[group.instance.id]": orders-service-pod-0
~~~

The `group.instance.id` value must be unique within the group. If two instances use the same ID, Kafka may fence/evict one member due to duplicate static identity. When running multiple replicas, generate the ID based on an ordinal or stable instance identifier rather than using a shared value across all pods.

Static membership does not eliminate rebalances when partition topology or subscriptions change. Nor does it replace heartbeats, session timeouts, and `max.poll.interval.ms`. You must account for shutdown duration, restart duration, and whether the instance will actually return.

## 12. Configurations Affecting Membership and Rebalances

| Property | Role | Considerations |
|---|---|---|
| group.id | Identifies the consumer group | Members sharing load must use the same group ID. |
| partition.assignment.strategy | Selects the assignor | Members must have compatible configurations. |
| heartbeat.interval.ms | Heartbeat interval under the classic protocol | Typically must be smaller than `session.timeout.ms`; values that are too small increase traffic. |
| session.timeout.ms | Time the coordinator waits for a heartbeat before removing a member under the classic protocol | Too low can trigger rebalances on brief network glitches; too high slows down recovery. |
| max.poll.interval.ms | Maximum interval between poll calls | Processing a batch for too long can cause the consumer to be considered stalled and removed from the group. |
| max.poll.records | Maximum number of records returned in one poll | A batch that is too large can lengthen processing time and impact `max.poll.interval.ms`. |
| group.instance.id | Static member identifier | Must be unique within the group. |
| partition.assignment.strategy | Supported assignor list | Must remain compatible during rolling upgrades. |

Heartbeat and session timeout parameters behave differently depending on the group protocol. With the classic protocol, `heartbeat.interval.ms` and `session.timeout.ms` are key parameters for coordinating membership. With the new consumer group protocol, certain parameters and responsibilities are managed differently. Check the Kafka client documentation for your exact version rather than copying configurations across versions.

`max.poll.interval.ms` is especially important when listeners have long processing times. If a consumer polls too infrequently, the group may evict the member and reassign its partitions to another consumer. When the old consumer eventually completes the slow task, it can produce duplicate side effects if the application does not enforce ownership checks and idempotency.

## 13. Monitoring Ownership and Rebalances in Production

To understand which member owns a partition, you need to observe group state, members, and lag. Useful Kafka CLI commands include:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group orders-service
~~~

The `describe` command displays topic, partition, committed offset, log end offset, and lag in the format supported by your Kafka version.

To view more detailed member and assignment information, many Kafka versions support:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group orders-service \
  --members \
  --verbose
~~~

Depending on the version, you can also use the command to inspect group state:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group orders-service \
  --state
~~~

CLI options may vary across Kafka distributions and versions. Check `kafka-consumer-groups.sh --help` in your operating environment.

You should monitor:

- Current member count and group state.
- Partition assignments per member.
- Rebalance frequency and rebalance completion duration.
- Consumer lag per partition, not just total lag.
- Number of partitions without a consumer owner when the group is stable.
- Listener processing duration and intervals between polls.
- Logs for partition revoked, assigned, and lost events.
- Commit failure rates and the number of records reprocessed after a rebalance.

Spring Kafka allows configuring logs and listeners to record assignments. When investigating, log the group ID, client ID, member ID, partition, and generation if available from consumer metadata. Do not log sensitive payloads merely to track rebalances.

## 14. Common Operational Scenarios

### New consumers joining and the group rebalancing continuously

If an autoscaler frequently creates and deletes pods, group membership changes continuously. Eager rebalances can pause processing on many partitions on every change. Review scaling policies, readiness probes, graceful shutdown, cooperative assignors, and static membership where appropriate.

### One consumer receives more partitions than others

Check the assignor, member subscriptions, and partition counts per topic. `RangeAssignor` can create overall imbalance when multiple topics are divided independently. `RoundRobin` or `Sticky` may be more suitable, though they should be tested with actual subscriptions.

### Some consumers have no partitions

If the number of consumers exceeds the number of eligible partitions, this is normal behavior. Check concurrency and replica counts to avoid spawning too many idle consumers. If the topic has plenty of partitions yet a consumer still receives none, check subscriptions, group ID, and member status.

### Consumer is evicted from the group during slow record processing

Measure the processing time per poll batch. Reduce `max.poll.records`, optimize the listener, increase `max.poll.interval.ms` if appropriate, and avoid long blocking operations on the consumer thread. If offloading work to an asynchronous executor, manage offsets and ownership carefully because the listener may return before business processing actually finishes.

### Records are processed multiple times after a rebalance

Check the latest committed offset, ack mode, when the listener completed, and when the partition was revoked. Design consumers to be idempotent by event ID to safely handle redelivered records. Rebalances do not create duplicates in the log by themselves; observed duplicates usually result from re-reading uncommitted records or executing side effects before offsets are committed.

### Prolonged rebalances

Check revoke callback duration, listener processing time, partition count, assignor, heartbeats, session timeouts, and GC pauses or network interruptions. Do not arbitrarily set large timeouts to mask a hung listener; identify the root cause preventing the consumer from polling or sending heartbeats on time.

## 15. Common Misconceptions

**Each consumer always receives exactly one partition.** False. A consumer can own multiple partitions; some consumers may be assigned none if there are more members than partitions.

**Partition assignment is decided by the topic's broker leader.** False. The broker leader serves the partition; the group coordinator coordinates membership. The assignment algorithm is executed according to the group protocol and assignor in use.

**The group leader is the partition leader.** False. In the classic group protocol, the group leader is a consumer member that computes the assignment. The partition leader is a broker.

**Each consumer group can only have one consumer.** False. A group has multiple members to split partitions and process in parallel.

**Two groups cannot read the same partition.** False. Each group has its own offsets and assignments; multiple groups can read the same topic independently.

**Increasing concurrency always increases throughput.** False. Maximum parallelism also depends on partition count, broker capacity, listener processing, and downstream systems. Consumers beyond the partition count may receive no partitions.

**Cooperative rebalance eliminates disruption completely.** False. It reduces the number of partitions that must be revoked at once, but partitions changing owners still go through the revoke and assign process.

**A partition assigned to a consumer means its records have been processed.** False. Ownership only defines which member is responsible for reading the partition. Committed offsets and completed business work are separate states.

**Manual assignment still rebalances automatically like `subscribe()`.** False. When using `assign()`, the application is responsible for distribution and ownership transfers.

## 16. Design Guidelines

When designing a consumer group for a Spring Kafka workload, determine the required partition count, instance count, and parallelism upfront. Use the same group ID for consumers that need to share load; use separate group IDs for independent reading streams.

A deployment configuration can follow this sequence:

1. Choose the partition count based on throughput, business ordering requirements, and scalability.
2. Set a stable group ID for each independent processing stream.
3. Choose an assignor suited to the topic count, subscriptions, and acceptable disruption level.
4. Configure concurrency to match the partition count and processing resources.
5. Set heartbeat, session timeout, and `max.poll.interval.ms` based on the group protocol and actual processing times.
6. Use graceful shutdown so consumers have a chance to finish and revoke partitions cleanly.
7. Configure an ack mode and commit strategy aligned with business requirements.
8. Design idempotent consumers to handle records redelivered after rebalances.
9. Monitor members, assignments, rebalances, lag, and commit errors.
10. Test scale-up, scale-down, restart, network loss, and slow-listener scenarios.

Partition assignment determines which consumer is responsible for reading a partition; ownership changes with membership and rebalances. Understanding assignors, rebalance protocols, concurrency, and offsets enables systems to scale predictably, minimize pauses during ownership handoffs, and recover safely when consumers fail.

# Cooperative and Eager Rebalancing

## 1. What Is Rebalancing in a Consumer Group?

A Kafka consumer group divides a topic's partitions among consumer members sharing the same group ID. Each partition is assigned to at most one consumer in the same group at a given time. This assignment is called partition assignment.

Rebalancing is the process by which a group adjusts assignments when group or topic state changes. Common triggers include:

- A new consumer joins the group or an existing consumer leaves.
- A consumer crashes, loses connectivity, or fails to send heartbeats on time.
- A consumer fails to call `poll()` within the allowed window and is considered inactive.
- Consumer subscriptions change.
- A topic gains or changes partitions, or subscription-related metadata changes.
- The group coordinator needs to recover group state after a failure.

Rebalancing is a normal Kafka mechanism that distributes partitions among members and sustains processing when topology changes. However, it can temporarily pause consumption, increase consumer lag, and cause uncommitted records to be redelivered.

Two assignment strategies are commonly discussed:

- **Eager rebalancing**: revokes all current partition assignments before applying the new assignment.
- **Cooperative rebalancing**: revokes only the partitions that actually need to move to another consumer; partitions staying with their previous consumer can continue being held.

The difference lies in how currently owned partitions are revoked and redistributed. Both still use consumer group coordination and both can cause disruption during ownership transfers.

## 2. How Does Eager Rebalancing Work?

### 2.1. Revoking the entire assignment

With eager rebalancing, when the group needs to rebalance, participating consumers revoke all assigned partitions. Then the coordinator and partition assignor compute the new assignment and redistribute partitions across members.

Suppose topic `orders` has 6 partitions and the group has two consumers:

~~~text
Before rebalance

Consumer A: P0, P1, P2
Consumer B: P3, P4, P5
~~~

A consumer C joins. Under eager rebalancing, both A and B must give up their current assignments before receiving new assignments, even if some partitions eventually return to the same consumer.

~~~text
During eager rebalance

Consumer A: revoke P0, P1, P2
Consumer B: revoke P3, P4, P5
Consumer C: joining the group

After reassignment (example)

Consumer A: P0, P1
Consumer B: P3, P4
Consumer C: P2, P5
~~~

Between revocation and when the new assignment takes effect, consumers stop processing the revoked partitions. This is why eager rebalancing is often described as a group-wide stop-the-world pause for partition processing.

### 2.2. High-level sequence

In the classic consumer group protocol, the sequence can be understood as follows:

1. Consumers detect a rebalance is needed and enter group coordination.
2. Members synchronize subscription state and participate in the JoinGroup round.
3. The group leader/assignor computes the new assignment.
4. Members revoke old assignments under the eager protocol.
5. The new assignment is distributed via SyncGroup.
6. Consumers begin fetching and processing from the next offset per committed progress.

Protocol details and coordination mechanics may vary by Kafka version and active group protocol. The defining point of the eager protocol is that all old assignments must be revoked before the new assignment is applied.

### 2.3. Operational impact

Eager rebalancing has several consequences:

- **Broad processing pauses**: even consumers that lose no partitions in the final assignment must participate in revoking and re-receiving them.
- **Higher recovery latency**: processing can stall while members complete group coordination and receive assignments.
- **Increased likelihood of redelivery**: records already processed whose offsets were not yet committed may be redelivered after a rebalance.
- **Potential lag spikes**: when a group has many partitions or slow revoke callbacks, the pause grows longer.
- **Simpler assignment state**: all old assignments are cleared, which can make partition handover logic easier to reason about.

Eager rebalancing does not mean every record is processed twice. Duplicates only occur when processing progress was not committed or business side effects ran before offsets were saved. Consumers still require idempotent design.

## 3. How Does Cooperative Rebalancing Work?

### 3.1. Incremental revocation

Cooperative rebalancing uses an incremental model: consumers revoke only the partitions that need to move to other members. Partitions retained by the same consumer can continue being processed while the group completes redistributing the remaining partitions.

Using the same starting example with two consumers:

~~~text
Before rebalance

Consumer A: P0, P1, P2
Consumer B: P3, P4, P5
~~~

Consumer C joins the group. A balanced new assignment might need to move P2 from A and P5 from B to C. With cooperative rebalancing:

~~~text
First rebalance round

Consumer A: keep P0, P1; revoke P2
Consumer B: keep P3, P4; revoke P5
Consumer C: not yet receiving P2, P5 while old owner has not released them

Next round

Consumer A: P0, P1
Consumer B: P3, P4
Consumer C: P2, P5
~~~

Partitions P0, P1, P3, and P4 do not need to be revoked solely to reassign others. They can keep being processed by their current consumers. P2 and P5 are handed to C only after their prior owners have released them.

### 3.2. Why can multiple rounds be required?

A cooperative assignor cannot hand a partition to a new consumer while the previous consumer still holds it. Therefore, the transfer can take more than one rebalance round:

1. The assignor identifies partitions that must move.
2. Current owners receive an assignment excluding the partitions to release and revoke them accordingly.
3. Once old ownership is revoked, the group runs the subsequent distribution round.
4. New consumers receive the released partitions.

In typical cases, the handover completes after one revocation round and one subsequent assignment round. With multiple simultaneous changes or complex assignments, the actual number of rounds depends on topology and the assignor.

Cooperative rebalancing prioritizes ownership safety: a new consumer never starts processing a partition before the old consumer releases it.

### 3.3. CooperativeStickyAssignor

`CooperativeStickyAssignor` is Kafka's partition assignor that supports the cooperative protocol while attempting to keep assignments stable across rebalances.

This assignor combines two objectives:

- **Balance**: distributes partitions relatively evenly across consumers.
- **Stickiness**: keeps partitions on current consumers if movement is unnecessary, minimizing partition transfers.

Stickiness helps when consumers frequently join or leave the group or when the group has many partitions. If a new consumer joins, the assignor can move only a necessary subset of partitions rather than reshuffling the entire assignment.

`CooperativeStickyAssignor` does not eliminate rebalances. It narrows the set of partitions requiring revocation and can reduce disruption duration. If members in the group keep churning continuously or consumers process slowly, the group will still experience frequent rebalances and lag can still grow.

## 4. Comparing Eager and Cooperative

| Criterion | Eager rebalancing | Cooperative rebalancing |
|---|---|---|
| Revocation scope | Entire current partition assignment | Only partitions that need to move |
| Partitions without owner change | Still revoked and reassigned | Can stay on current owner |
| Disruption scope | Typically broader | Typically narrower |
| Handover rounds | Usually one revoke-and-assign cycle | May require multiple incremental rounds |
| Operational complexity | Simpler model | Requires compatible assignor and members |
| Ability to curb rebalance lag | Limited for large groups | Can reduce processing pause time |
| Continuity | Group pauses broadly during rebalance | Unmoved partitions can keep processing |
| Safety | Waits for old assignment revocation before new assignment | Assigns partitions only after old owner releases |

Do not interpret cooperative as zero downtime or zero duplicates. It shrinks partition revocation scope, yet partitions being transferred can still pause temporarily. If a listener executed side effects without committing offsets, redelivery can still happen.

## 5. Partition Assignors Determine Distribution

Kafka consumers use a partition assignor to compute which consumer receives which partition. Rebalance protocol and assignment strategy are related, but not the same concept:

- **Rebalance protocol** governs how the group revokes and applies assignments.
- **Partition assignor** governs how partitions are distributed across members.

Common assignors:

| Assignor | Distribution approach | Rebalance protocol |
|---|---|---|
| `RangeAssignor` | Splits partitions by range per topic | Eager |
| `RoundRobinAssignor` | Alternates partitions across consumers | Eager |
| `StickyAssignor` | Tries to preserve assignments on redistribution | Eager |
| `CooperativeStickyAssignor` | Balances and preserves assignments via incremental revocation | Cooperative |

`StickyAssignor` and `CooperativeStickyAssignor` share the goal of assignment stability yet use different protocols. You cannot switch just one member's assignor name and assume the whole group has moved to cooperative mode.

Within a group, members must negotiate a compatible assignor/protocol. If members run differing configs during a rollout, Kafka must select a common strategy supported by all members; incompatible configs can cause rebalances to fail or behave unexpectedly.

## 6. Configuring Cooperative Rebalancing in Spring Kafka

### 6.1. Spring Boot configuration

With a Kafka client supporting `CooperativeStickyAssignor`, you can declare:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-service
      properties:
        partition.assignment.strategy: org.apache.kafka.clients.consumer.CooperativeStickyAssignor
      enable-auto-commit: false
    listener:
      ack-mode: record
~~~

Spring Boot's `spring.kafka.consumer.properties` forwards custom Kafka client properties to the consumer. The Kafka client property name is `partition.assignment.strategy`.

If using `application.properties`:

~~~properties
spring.kafka.consumer.group-id=orders-service
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.consumer.properties.partition.assignment.strategy=org.apache.kafka.clients.consumer.CooperativeStickyAssignor
spring.kafka.listener.ack-mode=record
~~~

Check the Kafka client version managed by Spring Boot. `CooperativeStickyAssignor` was introduced in Kafka 2.4; older applications may lack this class or cooperative protocol support. Do not check only the Spring Kafka version; check the actual `kafka-clients` version in your dependency tree.

### 6.2. Java ConsumerFactory configuration

If constructing the consumer factory manually:

~~~java
Map<String, Object> properties = new HashMap<>();

properties.put(
    ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
    "localhost:9092"
);
properties.put(
    ConsumerConfig.GROUP_ID_CONFIG,
    "orders-service"
);
properties.put(
    ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
    false
);
properties.put(
    ConsumerConfig.PARTITION_ASSIGNMENT_STRATEGY_CONFIG,
    CooperativeStickyAssignor.class.getName()
);

ConsumerFactory<String, OrderCreated> consumerFactory =
    new DefaultKafkaConsumerFactory<>(properties);
~~~

Then ensure the listener container uses this exact factory. In applications with multiple consumer factories or multiple `@KafkaListener`s, do not assume one configuration applies to every container.

### 6.3. Do not confuse concurrency with rebalance strategy

Spring Kafka can create multiple consumers in a listener container via the `concurrency` attribute. Example:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-service",
    concurrency = "3"
)
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

`concurrency` sets the number of consumer threads created by the container. It does not select eager vs. cooperative protocol. Rebalance strategy is controlled by the Kafka consumer property `partition.assignment.strategy`.

The number of consumers able to process in parallel remains bounded by assigned partitions. If the topic has 3 partitions, raising concurrency to 8 does not make 8 consumers process a single partition concurrently in the same group.

## 7. Migrating from Eager to Cooperative

The transition must be coordinated across members in the same consumer group. One member running an eager assignor while another runs a cooperative assignor can prevent the group from agreeing on a protocol.

A common rollout pattern uses two phases, keeping the existing eager assignor alongside the cooperative assignor in the supported list:

**Phase 1: deploy clients supporting both assignors**

~~~properties
partition.assignment.strategy=org.apache.kafka.clients.consumer.RangeAssignor,org.apache.kafka.clients.consumer.CooperativeStickyAssignor
~~~

Roll out instances safely one step at a time. During this phase, `RangeAssignor` is listed first so the group can still select eager assignment while all members support that list.

**Phase 2: switch to cooperative**

Once all members run the Phase 1 configuration and the group stabilizes, update the config to use only:

~~~properties
partition.assignment.strategy=org.apache.kafka.clients.consumer.CooperativeStickyAssignor
~~~

Continue rolling out instances. Once every member supports the cooperative assignor and the group negotiates this strategy, the group transitions to cooperative rebalancing.

This is a common migration pattern for the classic consumer group protocol. Check upgrade guidance for your Kafka client and framework versions, especially when multiple applications share a group ID or members are not deployed together.

Before rolling out:

1. List all applications and instances using the group ID.
2. Confirm the Kafka client version supports the cooperative assignor.
3. Inspect the current assignor list and how the framework builds consumer properties.
4. Deploy the dual-assignor phase to every member.
5. Verify the group is stable with no older members remaining.
6. Switch to the cooperative-only assignor in a controlled rollout.
7. Monitor rebalance counts, rebalance durations, consumer lag, and callback errors.

Avoid changing the assignor at the same time as changing group ID, increasing partition counts, and altering commit policies unless necessary. Multiple simultaneous changes make root-cause analysis difficult if the group becomes unstable.

## 8. ConsumerRebalanceListener and Partition Lifecycle

Kafka provides `ConsumerRebalanceListener` so applications are notified when partitions are revoked and assigned. The two core callbacks are:

- `onPartitionsRevoked(...)`: the consumer is about to lose some or all partitions.
- `onPartitionsAssigned(...)`: the consumer has just received an assignment.

Some Kafka versions also include `onPartitionsLost(...)` to signal partitions lost ownership without a normal revoke process. Check the API for your Kafka client version.

Basic listener example:

~~~java
public class OrderRebalanceListener implements ConsumerRebalanceListener {

    @Override
    public void onPartitionsRevoked(
        Collection<TopicPartition> partitions
    ) {
        log.info("Partitions revoked: {}", partitions);
        // Complete finishable work and handle offsets
        // according to the application's commit policy.
    }

    @Override
    public void onPartitionsAssigned(
        Collection<TopicPartition> partitions
    ) {
        log.info("Partitions assigned: {}", partitions);
        // Initialize local state for newly received partitions.
    }

    @Override
    public void onPartitionsLost(
        Collection<TopicPartition> partitions
    ) {
        log.warn("Partitions lost: {}", partitions);
        // Do not assume the consumer still has authority to commit for these partitions.
    }
}
~~~

In cooperative rebalancing, the `partitions` list in the revoke callback may contain only the partitions being transferred. The application must not assume the callback always receives the entire assignment.

### 8.1. Work to perform on revoke

When a consumer prepares to release partitions, the application may need to:

- Stop accepting new work for partitions about to be revoked.
- Finish or cancel in-flight work according to policy.
- Flush local state or pending writes to external systems.
- Commit final offsets if the application manages commits manually and still holds partition ownership.
- Release resources tied to those partitions.

Never wait indefinitely in a revoke callback. A prolonged callback delays the group rebalance, forcing other consumers to wait and increasing lag.

With `onPartitionsLost`, partitions may already have been assigned to another member. Never assume you can commit offsets or perform a normal handover as in a standard revoke callback.

### 8.2. Work to perform on assigned

When receiving partitions, the consumer may need to create local state, warm caches, or start tracking the new partitions. Under the cooperative protocol, the assigned callback can be called across incremental rebalance rounds; the application must process only the delta provided rather than assuming it receives all partitions every time.

Do not reinitialize all consumer state when only one new partition is assigned. Use a map keyed by `TopicPartition` or an equivalent state-management structure to update only the affected slice.

## 9. ConsumerAwareRebalanceListener in Spring Kafka

Spring Kafka provides `ConsumerAwareRebalanceListener`, extending Kafka's rebalance callbacks with access to the consumer inside callbacks. It also provides hooks to coordinate revocation timing with container commits.

Common hooks include:

- `onPartitionsRevokedBeforeCommit(...)`: invoked before the container executes the final offset commit for the revoke cycle.
- `onPartitionsRevokedAfterCommit(...)`: invoked after the container completes that commit.
- `onPartitionsAssigned(...)`: invoked when partitions are assigned.
- `onPartitionsLost(...)`: invoked when partitions are lost in supported versions.

Skeleton implementation example:

~~~java
public class OrderConsumerRebalanceListener
        implements ConsumerAwareRebalanceListener {

    private static final Logger log =
        LoggerFactory.getLogger(OrderConsumerRebalanceListener.class);

    @Override
    public void onPartitionsRevokedBeforeCommit(
        Consumer<?, ?> consumer,
        Collection<TopicPartition> partitions
    ) {
        log.info("Revoking before commit: {}", partitions);
        // Prepare local state before container-managed commit.
    }

    @Override
    public void onPartitionsRevokedAfterCommit(
        Consumer<?, ?> consumer,
        Collection<TopicPartition> partitions
    ) {
        log.info("Revoked after commit: {}", partitions);
        // Release resources of released partitions.
    }

    @Override
    public void onPartitionsAssigned(
        Consumer<?, ?> consumer,
        Collection<TopicPartition> partitions
    ) {
        log.info("Assigned: {}", partitions);
        // Initialize state for newly received partitions.
    }

    @Override
    public void onPartitionsLost(
        Consumer<?, ?> consumer,
        Collection<TopicPartition> partitions
    ) {
        log.warn("Lost: {}", partitions);
        // Clean up local state; do not commit as if still owning partitions.
    }
}
~~~

Callback names and signatures can vary by Spring Kafka version. Check the Javadoc of your dependency version before implementing.

You can register the listener on `ContainerProperties`:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        orderKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory
        ) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    factory.getContainerProperties()
        .setConsumerRebalanceListener(
            new OrderConsumerRebalanceListener()
        );

    return factory;
}
~~~

Then bind the factory to a listener:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-service",
    containerFactory = "orderKafkaListenerContainerFactory"
)
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

When the Spring listener container manages commits, avoid committing offsets manually inside callbacks in a way that conflicts with the acknowledgment mode. The `BeforeCommit` and `AfterCommit` hooks let the application coordinate local work with the container's commit cycle without accidentally creating two offset owners.

## 10. How Does Cooperative Rebalancing Affect Parallel Processing?

Cooperative rebalancing lets unmoved partitions keep running, yet the application must still manage in-flight work on revoked partitions.

For example, a listener processes a batch from P2 while P2 is about to move from consumer A to consumer C. If A still has an asynchronous background task running after the revoke callback finishes, that task might continue writing to the database or emitting events even after C starts processing P2. This can cause concurrent processing of the same partition and violate business-layer ordering assumptions.

For asynchronous processing:

- Track tasks by `TopicPartition`.
- When a partition is revoked, stop spawning new tasks for that partition.
- Settle or cancel running tasks within a deadline.
- Commit offsets only for contiguously completed records in required order.
- Prevent old tasks from continuing side effects after the partition has transferred.
- Use event IDs and idempotent operations in case tasks are redelivered after failures.

The cooperative protocol guarantees partition ownership transfer at the Kafka level. It does not manage background threads, queues, or side effects created by the application.

## 11. Other Configurations Affecting Rebalance Frequency

Cooperative rebalancing reduces revocation scope, yet the root causes of rebalances still need attention. Important consumer configurations:

| Configuration | Effect |
|---|---|
| `session.timeout.ms` | Time coordinator waits for heartbeats before marking member disconnected |
| `heartbeat.interval.ms` | Consumer heartbeat frequency under the classic protocol |
| `max.poll.interval.ms` | Time limit between poll calls during consumer processing |
| `max.poll.records` | Maximum records returned in a single poll |
| `partition.assignment.strategy` | Selects assignor and partition distribution behavior |
| `group.instance.id` | Enables static membership for stably identified consumer members |
| `group.initial.rebalance.delay.ms` | Initial wait window to batch joining members under the classic protocol |

Exact values and effects depend on the group protocol and Kafka client version. For instance, heartbeat/session behavior can differ under the new consumer protocol compared to the classic protocol.

Raising `session.timeout.ms` does not fix a slow listener if the consumer violates `max.poll.interval.ms`. Raising `max.poll.interval.ms` also does not fix heartbeat failures caused by broker or network issues. Identify which timeout is triggering rebalances before tuning.

`group.instance.id` can reduce unnecessary rebalances when an instance restarts briefly and returns with the same identity. However, static membership does not replace a cooperative assignor; they solve different problems.

## 12. Operational Scenarios and Investigation

| Symptom | Eager rebalancing | Cooperative rebalancing | What to inspect |
|---|---|---|---|
| Adding a consumer | Entire assignment may be revoked | Only partitions needing transfer are revoked | Check member join and assignments |
| One consumer leaves group | Remaining members revoke and re-receive all assignments | Leaving member's partitions redistribute incrementally | Check shutdown and session timeout |
| Slow listener processing | Can breach max poll interval and cause wide rebalance | Still triggers rebalance; partitions revoked incrementally | Measure processing time and poll interval |
| Topic adds partitions | Group must distribute new partitions and may reassign | Can append new partitions or move only necessary subset | Check metadata and assignments |
| Continuous consumer restarts | Group may rebalance continuously | Cooperative cuts redundant revocations but cannot stop churn | Check restarts, health checks, and static membership |
| Slow revoke callback | Slows the entire rebalance | Delays releasing moving partitions | Measure callback duration and cleanup work |

### 12.1. Continuous rebalances

If logs continuously record rebalances, identify the trigger:

- Pod/container restarts or misconfigured liveness probes.
- Flaky networking interrupting heartbeats.
- Slow listener processing exceeding `max.poll.interval.ms`.
- Consumer thread blocked by a database or external service.
- Group ID or subscription changing between deployments.
- Member count churning continuously due to autoscaling.

A cooperative assignor cannot cure a consumer repeatedly leaving the group. It only reduces the number of partitions revoked during each assignment change.

### 12.2. Prolonged rebalances

If rebalance durations are high, inspect:

- Duration of `onPartitionsRevoked` callbacks.
- Duration of `onPartitionsAssigned` callbacks.
- Partition count in the group and member count.
- Time taken by the group coordinator to process JoinGroup/SyncGroup.
- In-flight tasks requiring flushing or stopping.
- Metadata errors or coordinator communication issues.

In cooperative mode, multiple incremental rounds may occur. Measure total elapsed time from start until assignments stabilize, not just the duration of a single callback.

### 12.3. Duplicates after a rebalance

If a record appears twice after a rebalance, check:

1. Did the listener complete side effects before committing offsets?
2. Did the offset commit fail or remain pending when the partition was revoked?
3. Did an asynchronous task keep running after the partition was transferred?
4. Did the revoke callback flush or wait on tasks within a deadline?
5. Does the consumer enforce an idempotency key or unique constraint?

Rebalances can cause uncommitted records to be redelivered. This is normal at-least-once processing behavior. Consumers must handle duplicates safely rather than assuming every record is delivered only once.

## 13. Metrics and Logs to Monitor

To evaluate the benefits of cooperative rebalancing, track the same set of metrics before and after switching:

| Metric | What you need to know |
|---|---|
| Rebalance count | How many rebalances occur in the group |
| Rebalance duration | How long each rebalance lasts |
| Time without assigned partitions | How long consumers go without partitions |
| Partitions revoked | How many partitions are revoked per round |
| Partitions assigned | How many partitions are received per round |
| Consumer lag | Whether reading falls behind during rebalances |
| Poll interval / poll latency | Whether listeners run long or poll slowly |
| Heartbeat failures | Whether members miss heartbeats or drop coordinator connections |
| Listener processing duration | Whether business logic holds partitions too long |

Exact metric names depend on the Kafka client, Spring Kafka, Micrometer, and monitoring stack. Combine Kafka client metrics, Spring Kafka listener/container observations, and rebalance callback logs.

Logs should include group ID, member ID, topic-partition, and callback type. In cooperative mode, logging revoked/assigned partition lists helps confirm incremental assignments behave as expected. Avoid logging huge single lines containing the entire group assignment when partition counts are very large; log counts and emit full details at debug level.

## 14. Testing Cooperative and Eager Rebalancing

Test on a Kafka test broker or dedicated integration environment using topics and group IDs isolated from production data.

### 14.1. Eager scenario

1. Create a topic with 6 partitions.
2. Start consumers A and B in the same group with an eager assignor.
3. Record the initial assignment.
4. Start consumer C.
5. Observe `onPartitionsRevoked` and `onPartitionsAssigned` for A, B, and C.
6. Verify old assignments are fully revoked before the new assignment is applied.
7. Record the processing pause duration and consumer lag.

### 14.2. Cooperative scenario

1. Use the same topic and partition count, configuring all members with `CooperativeStickyAssignor`.
2. Start A and B and record the initial assignment.
3. Start C.
4. Observe partition lists in revoke and assigned callbacks across rounds.
5. Verify partitions that do not need to move stay on the old consumer.
6. Verify transferred partitions are received by the new consumer only after the old owner revokes them.
7. Compare pause duration and lag against eager under identical load conditions.

### 14.3. Testing member departure and failure handling

Beyond adding a consumer, test:

- Stopping a consumer with graceful shutdown.
- Killing a consumer abruptly to test `session.timeout.ms`.
- Introducing a slow listener to observe `max.poll.interval.ms`.
- Increasing the partition count.
- Running an asynchronous task in flight when a partition is revoked.
- Checking duplicates and committed offset state after a rebalance.

When comparing, hold partition count, throughput, concurrency, and processing duration constant. Changing multiple variables at once prevents attributing differences to the cooperative protocol.

## 15. Selection and Operational Principles

- Use eager when compatibility with legacy clients/assignors is required or a simple full-revocation model is preferred.
- Consider `CooperativeStickyAssignor` for large groups, high partition counts, or frequent membership changes where minimizing disruption matters.
- Ensure all members in the same group support and agree on the assignor/protocol before switching.
- Roll out in phases when migrating from eager to cooperative.
- Do not assume cooperative eliminates rebalances, duplicates, or consumer lag.
- Keep revoke callbacks short and bounded by deadlines; clean up transferring partition state properly.
- Distinguish `onPartitionsRevoked` from `onPartitionsLost`; never commit when ownership has already been lost.
- Monitor rebalance durations, revoked partition counts, consumer lag, and listener durations.
- Track asynchronous tasks by topic-partition so old tasks stop producing side effects after partitions transfer.
- Use consumer-side idempotency to handle redeliveries when offsets remain uncommitted.

Eager rebalancing revokes the entire assignment before redistributing, whereas cooperative rebalancing transfers partitions incrementally and preserves partitions that do not need to move. The right choice depends on client version, assignor, group scale, and how the application manages in-flight work when partitions are revoked.

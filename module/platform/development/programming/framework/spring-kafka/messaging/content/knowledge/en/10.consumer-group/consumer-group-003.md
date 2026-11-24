# Group Coordinator and Membership Management

## Lesson Objectives

In the **Consumer group** chapter, this lesson explains how Kafka coordinates consumers belonging to the same group through the group coordinator. The coordinator tracks members, processes heartbeats, manages generations, and coordinates rebalances to distribute partitions to active consumers.

**SPRING_KAFKA_MESSAGING** focuses on building applications that send and receive Kafka events with Spring Kafka, `KafkaTemplate`, and `@KafkaListener`; it also helps learners understand topics, partitions, offsets, consumer groups, serialization, retries, dead-lettering, transactions, exactly-once semantics, concurrency, and testing. Understanding the group coordinator helps explain why consumers are assigned partitions, why rebalances occur, and how to configure Spring Kafka so a group operates stably.

After this lesson, learners can:

- Explain the role of the group coordinator within a consumer group.
- Distinguish the group coordinator, group leader, Kafka controller, and broker.
- Describe how a consumer discovers the coordinator and joins a group.
- Understand member IDs, generation IDs, heartbeats, and membership state.
- Identify causes of rebalances and their impact on partition distribution.
- Distinguish eager rebalance from cooperative rebalance.
- Configure group membership and monitor consumer groups in Spring Kafka.
- Diagnose issues such as consumers continuously rebalancing, members being evicted, or partitions remaining unassigned.

## 1. A Consumer Group Needs a Coordination Mechanism

A Kafka topic can have multiple partitions. Within the same consumer group, each partition is assigned to at most one consumer at a time. Multiple consumers can read a topic together and share the work by receiving different partitions.

For example, the `commerce.order.created` topic has 6 partitions and the `billing-service` group has 3 consumers:

~~~mermaid
flowchart TB
    T["Topic: commerce.order.created"]
    T --> P0["Partition 0"]
    T --> P1["Partition 1"]
    T --> P2["Partition 2"]
    T --> P3["Partition 3"]
    T --> P4["Partition 4"]
    T --> P5["Partition 5"]
    P0 --> C1["Consumer 1"]
    P3 --> C1
    P1 --> C2["Consumer 2"]
    P4 --> C2
    P2 --> C3["Consumer 3"]
    P5 --> C3
~~~

To perform this distribution, Kafka needs to know:

- Which consumers are participating in the group.
- Which consumers are still active.
- Which topics each consumer subscribes to.
- Which partitions are assigned to each consumer.
- How assignments should change when a member joins or leaves.
- How far the group's reading progress has been committed on each partition.

Kafka uses a group coordinator to manage membership and coordinate partition distribution. Each consumer group has one coordinator responsible for coordinating that group.

## 2. What Is the Group Coordinator?

The group coordinator is a Kafka broker selected to manage a specific consumer group. The coordinator receives requests related to the group's membership, heartbeats, generations, rebalances, and offset commits.

The coordinator is not a separate process that applications must deploy. It is a role assumed by a broker for the groups assigned to it.

Key responsibilities:

- Accepting consumers joining or leaving the group.
- Tracking members via heartbeats.
- Managing group generation and state.
- Detecting members that are no longer active.
- Coordinating rebalances when membership or subscriptions change.
- Confirming that assignment synchronization is complete so the group transitions back to a stable state.
- Processing offset commit requests and storing the group's reading progress.

The coordinator gives all members a shared coordination point. Consumers do not independently negotiate partition assignments with one another; they participate in the group protocol managed by the coordinator.

### 2.1. How Is the Coordinator Selected?

Kafka stores consumer group committed offsets in the internal `__consumer_offsets` topic. A group ID is mapped to a partition of this internal topic. The broker currently acting as the leader of that corresponding partition assumes the group coordinator role for that group.

You can visualize it as:

~~~mermaid
flowchart TD
    A["Consumer group: billing-service"] --> B["Map group ID"]
    B --> C["Corresponding partition of __consumer_offsets"]
    C --> D["Leader broker of the partition"]
    D --> E["Group coordinator"]
    E --> F["Manage membership and offsets"]
~~~

This mechanism allows Kafka to distribute coordination responsibilities across brokers. Different groups can have coordinators on different brokers.

If the broker acting as coordinator fails, consumers must find the new coordinator. Kafka elects or determines the leader for the `__consumer_offsets` partition via its replication mechanism; the new leader broker can assume the coordinator role once metadata is updated.

### 2.2. The Group Coordinator Is Not the Kafka Controller

These two roles are easily confused, especially in clusters running KRaft.

| Component | Responsibility |
|---|---|
| Kafka broker | Handles producer/consumer requests, stores partition logs, and serves data |
| Group coordinator | Manages membership, heartbeats, rebalances, and offsets for a consumer group |
| Group leader in the classic protocol | Represents members to compute partition assignments and sends assignments in SyncGroup |
| KRaft controller | Manages cluster metadata and cluster state via the controller quorum |

The group coordinator is a broker-side role that coordinates consumer groups. The KRaft controller manages cluster metadata. These two roles can reside on different nodes and have different scopes of work.

### 2.3. Coordinator and Group Leader Are Different

In the classic consumer group protocol, the coordinator manages the group and selects one member as the group leader for a generation. The group leader typically runs the client-side partition assignor to compute assignments based on member subscriptions.

The group leader is neither the broker leader of data partitions nor the group coordinator.

With newer consumer group protocols, some assignment responsibilities can be moved to the server side. Therefore, the model where the group leader computes assignments mainly describes the classic protocol; check the protocol and Kafka client version in use when analyzing logs or configuration.

## 3. How a Consumer Discovers the Group Coordinator

When a consumer starts up and needs to join a group, it must determine which broker is acting as the coordinator.

High-level process:

1. The consumer connects to a broker from `bootstrap.servers`.
2. The consumer sends a `FindCoordinator` request with the group ID.
3. The broker returns the address of the broker acting as the group coordinator.
4. The consumer connects to the coordinator.
5. The consumer sends a request to join the group.
6. The coordinator manages membership and starts or completes a rebalance when needed.

~~~mermaid
sequenceDiagram
    participant C as Kafka Consumer
    participant B as Bootstrap Broker
    participant G as Group Coordinator

    C->>B: Connect to bootstrap
    C->>B: FindCoordinator(group.id)
    B-->>C: Coordinator host and port
    C->>G: Connect to coordinator
    C->>G: JoinGroup
    G-->>C: Membership result
~~~

If the coordinator changes due to a broker restart, leadership change on the `__consumer_offsets` partition, or cluster administrative events, the consumer may receive coordinator unavailable or not-coordinator errors. The Kafka client will rediscover the coordinator via its retry and metadata refresh mechanisms.

Applications do not need to call `FindCoordinator` manually. The Kafka consumer client and Spring Kafka handle this protocol.

## 4. Consumer Group Membership

Membership describes the set of consumers currently participating in a group. Each consumer member has its own identity information and state.

Key details:

| Component | Meaning |
|---|---|
| group.id | Consumer group identifier |
| member.id | Member identifier managed by Kafka within the group |
| group.instance.id | Stable identifier for a static member if configured |
| generation.id | Current membership version of the group |
| subscription | Topics or patterns subscribed by the member |
| assignment | Partitions assigned to the member |
| coordinator | Broker managing the group's membership |

### 4.1. group.id

`group.id` identifies consumers that share reading progress and participate in partition distribution together. Consumers with the same `group.id` and compatible subscription configurations can join the same group.

Examples:

~~~text
billing-service
inventory-service
notification-service
analytics-service
~~~

If `billing-service` has three instances with the same `group.id`, Kafka distributes partitions among those instances. If `analytics-service` uses its own group ID, it has independent reading progress and can read the entire stream that `billing-service` is also consuming.

Do not use a randomly changing group ID across deployments if you want to preserve reading progress. A new group ID usually means an independent reading progress.

### 4.2. member.id

`member.id` identifies a consumer within a group. With dynamic membership, Kafka assigns a member ID when the consumer joins. This ID is used in group requests such as heartbeat, leave, and sync.

When a consumer leaves the group and rejoins, its member ID may change. Applications should not use `member.id` as a business identifier or persist it as a long-term instance ID.

### 4.3. generation.id

`generation.id` represents a membership generation of the group. When the group goes through a rebalance and a new assignment is established, the generation can increment.

Member requests are typically tied to the current generation. Requests carrying an old generation can be rejected by the coordinator because membership has changed.

Generations help the coordinator detect requests from members belonging to an outdated group state, preventing a consumer from continuing to commit or heartbeat as if it still owned a revoked assignment.

### 4.4. Subscription and Assignment

Subscription indicates which topics or patterns a member wants to read. Assignment is the actual set of partitions given to the member after the distribution process.

These two concepts are not the same:

- A consumer may subscribe to a topic with 12 partitions.
- The group has 3 consumers.
- Each consumer receives a subset of partitions according to the assignor.
- A consumer only processes the partitions assigned to it in the group.

If one consumer subscribes to different topics than the rest of the members, the assignment depends on the entire group's subscriptions and the assignor. In production applications, design members of the same group with compatible subscription configurations to avoid unexpected assignments.

## 5. Classic Membership Protocol: JoinGroup and SyncGroup

In the classic consumer group protocol, joining a group typically consists of the following main requests.

### 5.1. JoinGroup

A consumer sends `JoinGroup` to the coordinator to register or join the group. The request contains the group ID, member information, subscription, and supported partition assignors.

The coordinator collects the members participating in the generation. When group conditions allow, the coordinator selects a group leader and returns membership information to the members.

### 5.2. Group Leader Computes the Assignment

In the classic protocol, the group leader receives the subscription details of all members. It uses a partition assignor to determine which partitions will be assigned to each member.

For example, a topic with 6 partitions and a group with 3 members:

~~~text
Member A -> partition 0, 3
Member B -> partition 1, 4
Member C -> partition 2, 5
~~~

This is an illustrative assignment. Actual assignments depend on the assignor, subscriptions, and the number of topics/partitions.

### 5.3. SyncGroup

The group leader sends the assignments to the coordinator via `SyncGroup`. The coordinator distributes the corresponding assignment to each member. Once members receive their assignments and the group finishes synchronization, the group transitions to a stable state.

~~~mermaid
sequenceDiagram
    participant A as Consumer A
    participant B as Consumer B
    participant G as Group Coordinator

    A->>G: JoinGroup(subscription)
    B->>G: JoinGroup(subscription)
    G-->>A: A is selected as group leader
    G-->>B: B is a follower
    Note over A: Compute assignment
    A->>G: SyncGroup(assignments)
    B->>G: SyncGroup
    G-->>A: Assignment for A
    G-->>B: Assignment for B
    Note over A,B: Start consuming
~~~

With newer consumer group protocols, the assignment and rebalance flow may differ from the classic protocol. Do not assume all versions use the same group leader role and request sequence.

## 6. Heartbeats and Detecting Inactive Members

After joining a group, a consumer must maintain its membership. In the classic protocol, the consumer periodically sends heartbeats to the coordinator to prove it is still participating in the group.

Common properties:

| Property | Meaning |
|---|---|
| heartbeat.interval.ms | Time interval between heartbeats |
| session.timeout.ms | Time the coordinator waits for a heartbeat before considering a member lost |
| max.poll.interval.ms | Maximum time between two polls before the consumer is considered no longer making progress |

### 6.1. heartbeat.interval.ms

The heartbeat interval determines how frequently the consumer sends heartbeats. Typically this value needs to be sufficiently smaller than the session timeout to tolerate network latency or periods of high load.

In the classic protocol, clients usually configure `heartbeat.interval.ms` smaller than `session.timeout.ms`. Exact values must comply with broker limits and recommendations for your Kafka version.

### 6.2. session.timeout.ms

If the coordinator does not receive a heartbeat within the session timeout, it can consider the member lost and initiate a rebalance so that the member's partitions are redistributed.

A session timeout that is too low makes the group sensitive to transient network glitches or brief pauses. A value that is too high slows down detection of genuinely dead consumers and prolongs the time partitions go unprocessed by other members.

### 6.3. max.poll.interval.ms

`max.poll.interval.ms` limits the time between two `poll()` calls. A consumer may still be sending heartbeats, but if the application takes too long to process and fails to call the next poll within the limit, the Kafka client can proactively leave the group or mark the member as no longer making progress, leading to a rebalance.

Key distinctions:

- `session.timeout.ms` monitors heartbeats and member liveness.
- `max.poll.interval.ms` monitors the consumer's poll-calling progress.
- `heartbeat.interval.ms` sets the heartbeat frequency in the classic protocol.

Increasing the session timeout does not automatically fix a listener whose processing exceeds `max.poll.interval.ms`.

### 6.4. Configuration Example

~~~yaml
spring:
  kafka:
    consumer:
      group-id: billing-service
      properties:
        heartbeat.interval.ms: 3000
        session.timeout.ms: 45000
        max.poll.interval.ms: 300000
~~~

These are illustrative values, not an optimal configuration for every system. Measure listener processing time, poll duration, network latency, and broker limits before tuning.

## 7. Consumer Group States

In the classic group protocol, the coordinator manages group states to orchestrate joining and rebalancing.

Common states:

| State | Meaning |
|---|---|
| Empty | The group has no active members |
| PreparingRebalance | The group is preparing to rebalance, waiting for members to join or complete transition steps |
| CompletingRebalance | The coordinator is finalizing assignment synchronization |
| Stable | Membership and assignments are stable |
| Dead | The group no longer exists or is being removed from management metadata |

Simplified lifecycle:

~~~mermaid
stateDiagram-v2
    [*] --> Empty
    Empty --> PreparingRebalance: Member joins
    PreparingRebalance --> CompletingRebalance: Join phase complete
    CompletingRebalance --> Stable: Assignment synchronized
    Stable --> PreparingRebalance: Member change / subscription change
    Stable --> Empty: Last member leaves
    Empty --> [*]
~~~

A group in the `Stable` state means assignments are established and members can continue consuming. If the group repeatedly transitions from `Stable` to `PreparingRebalance`, inspect member leaves, heartbeats, poll intervals, deployments, and subscriptions.

States displayed by administration tools may vary slightly depending on the Kafka version and group type. Read the state together with member count, assignments, consumer lag, and coordinator logs.

## 8. Rebalance: When Membership Changes

A rebalance is the process by which a group redistributes partitions when membership or assignment conditions change.

Common triggers:

- A new consumer joins the group.
- A consumer stops gracefully or sends a leave-group request.
- A consumer crashes or loses connectivity.
- Heartbeats are missed beyond the session timeout.
- A listener processes too slowly and exceeds `max.poll.interval.ms`.
- Topics are added or partition counts change.
- Consumer subscriptions change.
- Partition assignor or group configuration changes.
- The coordinator changes after a broker failure or leadership transfer of the offsets partition.

### 8.1. How Does Rebalancing Impact Processing?

When a rebalance occurs:

1. Consumers may pause processing of affected partitions.
2. Old partition assignments are revoked according to the active protocol.
3. The coordinator and assignor determine the new assignment.
4. Consumers receive their new partitions.
5. Consumers resume from the group's committed offset for each partition, if the offset is still valid.

Rebalancing can increase consumer lag and reduce throughput while the group is not yet stable. If it occurs continuously, consumers may not have enough time to catch up on the backlog.

### 8.2. Eager Rebalance

In an eager rebalance, members revoke all currently assigned partitions before the new assignment is established. This can cause a noticeable pause while the group redistributes partitions.

This approach is simple and widely supported, but it can cause major disruption when a group has many members or many partitions.

### 8.3. Cooperative Rebalance

Cooperative rebalance allows assignments to change incrementally and revokes only the partitions that need to move. Partitions that do not need to change can continue being processed.

The Kafka client provides `CooperativeStickyAssignor` to support cooperative incremental rebalancing in compatible configurations.

~~~mermaid
flowchart TD
    A["Membership changes"] --> B["Compute new assignment"]
    B --> C{"Rebalance protocol"}
    C -->|Eager| D["Revoke all assignments"]
    C -->|Cooperative| E["Revoke only partitions that must move"]
    D --> F["Synchronize new assignment"]
    E --> F
    F --> G["Consumers resume processing"]
~~~

To use a cooperative assignor, members in the group must have compatible assignor configurations. Before switching, check the Kafka client versions and configurations of all applications participating in the group.

Cooperative rebalance reduces the scope of disruption, but it does not eliminate all rebalances nor guarantee there will be no duplicates. Offsets and idempotency still must be designed properly.

## 9. Static Membership

By default, consumers typically use dynamic membership: on restart, a consumer may leave the group and rejoin with a new member ID. This can trigger a rebalance even when the instance only restarts briefly.

Static membership allows a consumer to declare a stable `group.instance.id`. The coordinator recognizes the member by this identifier and can retain its membership for a period when the instance is temporarily disconnected.

Example Kafka consumer configuration:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: billing-service
      properties:
        group.instance.id: billing-instance-1
~~~

With multiple instances, each static member must have a unique `group.instance.id` within the group. Do not use the same value for two concurrently running consumers; the coordinator can reject a member due to a duplicate instance ID.

### 9.1. Benefits

- Reduces unnecessary rebalances when an instance restarts quickly.
- Limits continuous partition movement during controlled deployments.
- Preserves a stable member identity across connections.

### 9.2. Trade-Offs

- If an instance genuinely dies, the group may wait until the session timeout before releasing membership.
- Requires managing stable and unique IDs for each member.
- A single fixed ID must not be shared across all replicas.
- You must verify how Spring Kafka creates consumers when a listener has `concurrency` greater than 1.

Static membership suits environments with stable instance identities, such as StatefulSets or nodes with explicit identities. For rapidly scaling workloads with constantly changing instances, dynamic membership may be more suitable.

## 10. The Partition Assignor Decides Distribution

The coordinator manages the group protocol; the assignor decides which partitions are assigned to which members.

Common assignors in the Kafka client:

| Assignor | High-level distribution method |
|---|---|
| RangeAssignor | Assigns partitions by range to each consumer per topic |
| RoundRobinAssignor | Distributes partitions in round-robin order across consumers |
| StickyAssignor | Balances assignments while trying to keep prior assignments to minimize partition movement |
| CooperativeStickyAssignor | Preserves stickiness and supports incremental cooperative rebalancing |

Example cooperative sticky configuration:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        partition.assignment.strategy: org.apache.kafka.clients.consumer.CooperativeStickyAssignor
~~~

Actual assignments depend on the number of members, partition counts, subscriptions, assignor, and protocol. Do not assume partitions are always divided evenly in every scenario.

### 10.1. Limited by the Number of Partitions

Within a consumer group, a partition is assigned to at most one consumer at a time. Therefore, the total number of consumers that can process data concurrently is bounded by the number of assigned partitions.

For example, a topic with 4 partitions:

| Consumers in group | Consumers with partitions | Consumers without partitions |
|---:|---:|---:|
| 1 | 1 | 0 |
| 2 | Up to 2 | 0 |
| 4 | Up to 4 | 0 |
| 6 | Up to 4 | At least 2 |

Increasing consumers beyond the partition count does not create additional parallelism for that topic. Extra consumers can still join the group, but they receive no partitions.

## 11. Configuring and Managing Membership with Spring Kafka

Spring Kafka uses the Kafka consumer client to join a group. Applications usually do not interact directly with the group coordinator; instead, the consumer factory and listener container configuration determine behavior.

### 11.1. application.yml Configuration

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: billing-service
      enable-auto-commit: false
      auto-offset-reset: earliest
      properties:
        session.timeout.ms: 45000
        heartbeat.interval.ms: 3000
        max.poll.interval.ms: 300000
        partition.assignment.strategy: org.apache.kafka.clients.consumer.CooperativeStickyAssignor
~~~

These properties play distinct roles:

- `group-id` identifies the consumer group.
- `enable-auto-commit=false` lets the listener container manage commits.
- `auto-offset-reset` only applies when there is no valid offset.
- `session.timeout.ms` and `heartbeat.interval.ms` affect inactive member detection in the classic protocol.
- `max.poll.interval.ms` limits the time between polls.
- `partition.assignment.strategy` selects the partition distribution strategy.

### 11.2. Declaring a Listener

~~~java
@Service
public class OrderListener {

    @KafkaListener(
        topics = "commerce.order.created",
        groupId = "billing-service"
    )
    public void handle(OrderCreated event) {
        // Handle event.
    }
}
~~~

`groupId` on `@KafkaListener` specifies the group for the endpoint. If omitted, the listener can use the group ID from the consumer factory or the corresponding default configuration.

The `id` attribute of `@KafkaListener` is the ID of the listener endpoint in Spring; it is not synonymous with `groupId`. Do not confuse bean names, listener IDs, and consumer group IDs.

### 11.3. Concurrency and Membership

You can set concurrency on the listener container:

~~~java
factory.setConcurrency(3);
~~~

Spring Kafka creates multiple child consumer containers for the same listener. Each consumer joins the group with its own consumer client. The coordinator manages each consumer as a member in the group.

If the application has 2 instances and each instance has a concurrency of 3, the group has 6 consumers in total. Partition assignment happens across all 6 consumers, not merely within each process.

Concurrency should be chosen based on partition count, processing time, downstream load, and ordering requirements. Changing concurrency can trigger a group rebalance as the member count changes.

### 11.4. Listener Lifecycle

The Spring Kafka listener container manages the consumer lifecycle:

- Creates the consumer from `ConsumerFactory`.
- Subscribes to topics or patterns.
- Joins the group and receives assignments.
- Polls records and invokes the listener.
- Manages acknowledgments/offsets according to configuration.
- Stops the consumer when the container stops or the Spring context shuts down.

The container manages the consumer on the application side. The group coordinator remains the broker responsible for membership and rebalancing.

## 12. Monitoring Consumer Groups with Kafka Tools

You can use `kafka-consumer-groups` to inspect groups, states, and assignments.

List groups:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list
~~~

View progress and lag:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-service \
  --describe
~~~

View group state:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-service \
  --describe \
  --state
~~~

On supported versions, you can view detailed members and assignments:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-service \
  --describe \
  --members \
  --verbose
~~~

Common columns when describing a group:

| Column | Meaning |
|---|---|
| GROUP | Consumer group name |
| TOPIC | Topic being consumed |
| PARTITION | Assigned partition |
| CURRENT-OFFSET | Group's committed offset |
| LOG-END-OFFSET | Current end offset of the partition |
| LAG | Difference between log end and committed offset |
| CONSUMER-ID | Consumer member identifier |
| HOST | Consumer host address |
| CLIENT-ID | Kafka consumer client ID |

When investigating a group, inspect state, member count, assignments, current offset, and lag together. A group in the `Stable` state with growing lag can still suffer from throughput or business-processing issues.

## 13. Diagnosing Membership Issues

| Symptom | Possible Cause | What to Check |
|---|---|---|
| Group continuously rebalances | Consumer restarts, heartbeat timeout, or poll taking too long | Check logs, `session.timeout.ms`, `max.poll.interval.ms`, and processing times |
| Coordinator unavailable | Coordinator broker restarted or offsets partition changed leader | Check broker health and `__consumer_offsets` status |
| Member fenced | Duplicate static member ID or an old member is still active | Check `group.instance.id` and running instances |
| Consumer receives no partitions | More consumers than partitions or incompatible subscriptions/assignments | Check group describe output and assignor |
| Consumer loses membership after long processing | Failed to call poll within `max.poll.interval.ms` | Measure listener duration and adjust processing/batch size |
| Group never reaches Stable | Members fail to complete JoinGroup/SyncGroup or prolonged rebalancing | Check coordinator logs, members, and protocol |
| Partitions move repeatedly across members | Changing membership or assignor not preserving assignments | Check deployments, autoscaling, and assignor |
| Lag grows despite Stable group | Slow consumer processing, hot partition, or overloaded downstream | Measure per-partition lag and processing time |

### 13.1. Coordinator Unavailable

Coordinator unavailable errors can appear when the broker acting as coordinator is temporarily unreachable. The Kafka client typically retries finding the coordinator. If the error persists, check:

- Whether the coordinator broker is running.
- Whether the leader of the `__consumer_offsets` partition is stable.
- Whether the network between consumers and brokers is interrupted.
- Whether DNS, `advertised.listeners`, and security protocols are configured correctly.
- Whether broker logs show replication or storage errors.

Do not change the group ID just to work around a coordinator error. Changing the group ID creates a new reading progress and can cause consumers to re-read or skip data depending on the reset policy.

### 13.2. Continuous Rebalancing

Continuous rebalancing can leave consumers without enough time to process the backlog. Find the root cause:

- Instances restarting continuously due to health check failures or application errors.
- A listener taking too long to process a batch.
- Downstream timeouts delaying poll calls.
- `session.timeout.ms` set too low relative to actual latency.
- Deployments causing member counts to change frequently.
- Static membership configured with unstable or duplicate IDs.

Increasing timeouts can reduce false rebalances under high load, but it also slows down detecting dead consumers. Measure and choose appropriate values.

## 14. Observing and Operating the Group Coordinator

Signals to monitor:

| Signal | Meaning |
|---|---|
| Group state | Whether the group is stable or rebalancing |
| Member count | Number of participating consumers |
| Partition assignment | Distribution of partitions across members |
| Rebalance rate | How frequently the group must redistribute |
| Rebalance duration | Time to complete a rebalance |
| Consumer lag | Processing delay by group and partition |
| Heartbeat failures | Signs of network or member instability |
| Poll interval / processing time | Consumer ability to sustain polling |
| Coordinator errors | Connection errors or coordinator transitions |

Spring Kafka emits application events related to listener containers and partition assignments. You can combine these events with Kafka client metrics, logs, and dashboards to monitor group state.

Do not monitor only aggregate lag. Per-partition lag helps detect a hot partition while other partitions continue processing normally.

## 15. Membership Management Checklist

- [ ] Is `group.id` stable and managed according to consumption purpose?
- [ ] Do consumers in the same group have compatible subscriptions?
- [ ] Is it clear which broker is acting as the group coordinator?
- [ ] Is the coordinator distinguished from the group leader and KRaft controller?
- [ ] Do consumers maintain heartbeats within appropriate limits?
- [ ] Does listener processing time stay within `max.poll.interval.ms`?
- [ ] Are generations and membership allowed to stabilize across rebalances?
- [ ] Does the partition assignor fit balancing and disruption-reduction needs?
- [ ] If using static membership, is `group.instance.id` unique and stable?
- [ ] Does concurrency stay within useful parallelism based on partition counts?
- [ ] Are metrics available for group state, members, assignments, lag, and rebalances?
- [ ] Are procedures defined for handling coordinator unavailable and consumer fencing?
- [ ] Have consumer join, leave, crash, restart, and instance scaling scenarios been tested?

## Conclusion

The group coordinator is the broker responsible for managing membership, heartbeats, generations, rebalances, and offsets for a consumer group. Consumers locate the coordinator via `FindCoordinator`, join the group, and receive partition assignments according to the active protocol and assignor. In the classic protocol, `JoinGroup` and `SyncGroup` coordinate member gathering and assignment synchronization; heartbeats enable the coordinator to detect inactive members.

Spring Kafka uses the Kafka consumer client and listener containers to manage the consumer lifecycle. Applications need to keep group IDs stable, choose appropriate timeouts, avoid overly long listener processing, configure assignors deliberately, and monitor rebalances. By understanding the coordinator, membership, and assignments, learners can diagnose unstable groups, scale consumers appropriately, and operate reliable messaging pipelines.

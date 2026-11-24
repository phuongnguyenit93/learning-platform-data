# Multiple Instances in the Same Group

In Kafka, multiple consumer instances can join the same consumer group to share the work of processing a topic's data. This is the common way to scale a Spring Kafka application horizontally: run multiple replicas of the application, configure them with the same `group.id`, and let Kafka distribute partitions among active consumers.

Consumer groups provide load sharing and recovery when a member leaves the group. Each partition of a topic is assigned to at most one consumer in the same group at a given time. One consumer can receive multiple partitions, while a consumer assigned no partitions can still exist in the group without processing data. Thus, the partition count is a key limit on a group's parallelism.

## 1. What Is a Consumer Group?

A consumer group is a set of consumers sharing the same `group.id` identifier. Kafka treats these consumers as members collaborating to read a set of topics. The group coordinator tracks membership and manages partition distribution.

For example, an application runs three replicas:

```text
                 Topic: orders
             P0   P1   P2   P3   P4   P5
              \    |    |    |    |   /
               \   |    |    |    |  /
                Consumer group: order-service
                   /       |       \
                  /        |        \
             Instance A  Instance B  Instance C
```

All three instances use the same `group.id=order-service`. Kafka assigns partitions to the three member consumers. One illustrative distribution is:

| Consumer member | Assigned partitions |
|---|---|
| Instance A | `orders-0`, `orders-1` |
| Instance B | `orders-2`, `orders-3` |
| Instance C | `orders-4`, `orders-5` |

This is only an example distribution. Actual assignments depend on subscribed topics, partition counts, members in the group, and the configured partition assignment strategy.

Each partition has only one owning consumer within the group at a time. This rule helps Kafka preserve processing order within a partition and prevents two consumers in the same group from reading the same partition concurrently. A consumer can own multiple partitions if there are more partitions than consumers.

## 2. Multiple Instances Must Use the Same group.id

For replicas of the same service to share load, all of them must use the same stable `group.id`. `group.id` is the logical name of the consumer group, not an individual machine or pod ID.

Spring Boot configuration example:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-service
      enable-auto-commit: false
      auto-offset-reset: earliest
```

When deploying three replicas of the same application, all three replicas receive the `group-id: order-service` setting. Each replica creates its own consumer, and Kafka places those consumers into the same group.

```text
Pod order-service-1  ─┐
Pod order-service-2  ─┼── group.id = order-service
Pod order-service-3  ─┘
```

If a random or distinct group ID is assigned to each replica, Kafka treats them as independent groups. Each independent group can read all partitions of the topic, so every replica may receive the same event. That creates fan-out behavior rather than load sharing.

Conversely, if two services with different business responsibilities share the same group ID, Kafka distributes partitions between them. An event may only be received by one of the two services. When both services need to receive every event, each service must use its own group ID.

## 3. Same Group to Share Load, Different Group to Receive Independently

Suppose topic `orders` has six partitions and there are two requirements: updating inventory and generating revenue reports.

<table>
  <table-row>
    <table-cell width="30%">
      **Consumer group**
    </table-cell>
    <table-cell>
      **Behavior**
    </table-cell>
  </table-row>
  <table-row>
    <table-cell>
      `inventory-service`
    </table-cell>
    <table-cell>
      Three replicas in the same group share six partitions. Each record is processed by one member in the group according to the current assignment.
    </table-cell>
  </table-row>
  <table-row>
    <table-cell>
      `revenue-reporting`
    </table-cell>
    <table-cell>
      An independent group also reading topic `orders`. Members in this group share the group's own partitions, so reporting still receives every record the group can read.
    </table-cell>
  </table-row>
</table>

The two groups maintain separate committed offsets. How far `inventory-service` has read does not alter the progress of `revenue-reporting`. Each group can process the same record at different times and at different consumption rates.

| Configuration approach | Outcome |
|---|---|
| Multiple instances with the same `group.id` | Share partitions and split load within the same group. |
| Multiple instances with different `group.id` | Each group reads independently; can receive all data from the topic. |
| Different logical services sharing `group.id` | Services compete for partitions; neither service is guaranteed to receive every record. |

This is a key architectural decision. Choose group IDs by the logical processing unit that needs independent reading progress, not by machine name or replica count.

## 4. Partition Count Limits Parallel Consumers

Within the same group, a partition is assigned to only one consumer member. Therefore, the number of consumers that can concurrently receive data from a topic is bounded by that topic's partition count.

For example, a topic with four partitions:

| Consumers in group | Possible outcome |
|---:|---|
| 1 | One consumer receives all four partitions. |
| 2 | Two consumers split the four partitions. |
| 4 | Each consumer can receive one partition. |
| 6 | Up to four consumers have partitions; the remaining two consumers have no partitions to process. |

Increasing replicas from four to six does not make one partition processed in parallel by two consumers in the same group. If higher parallelism is needed, evaluate partition count, data partitioning capability, and downstream system capacity.

Increasing partitions affects key distribution. Producers often use a record key so events for the same entity land in the same partition to preserve relative order. When partitions are added, the key-to-partition mapping can change; new events for a key may be written to a different partition than older events. Therefore, adding partitions must be evaluated alongside ordering requirements and how the application handles existing data.

Partition count is also not the sole determinant of throughput. If a database can only handle a fixed rate of transactions, adding consumers can overload the database without increasing business completion speed. Measure throughput, latency, and dependency capacity before scaling out the group.

## 5. One Spring Kafka Process Can Create Multiple Consumers

In Spring Kafka, distinguish between application replica count and listener container `concurrency`:

- Each replica is an independent application process or container.
- `concurrency` creates multiple child consumer containers for a listener endpoint inside each replica.
- Each child consumer container has its own Kafka consumer and poll loop, joining the group with the endpoint's group ID.

Example deploying three replicas and setting concurrency to two:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-service
    listener:
      concurrency: 2
```

```text
Replica 1: consumer 1A, consumer 1B ─┐
Replica 2: consumer 2A, consumer 2B ─┼── group order-service
Replica 3: consumer 3A, consumer 3B ─┘

Maximum total consumer members: 3 replicas × 2 = 6
```

If the topic has six partitions, all six consumer members can receive partitions concurrently. If the topic only has four partitions, at most four members are assigned partitions; the remaining two members have no data to process. Actual consumer counts also depend on whether the listener endpoint is enabled, its subscription, and container configuration.

Concurrency can be set directly on the listener:

```java
@KafkaListener(
    topics = "orders",
    groupId = "order-service",
    concurrency = "2"
)
public void consume(OrderCreated event) {
    orderService.handle(event);
}
```

When using `groupId` in `@KafkaListener`, that value defines the group for the endpoint and can override the group ID inherited from the consumer factory. All replicas running the same configuration version must use the same value. When using the shared config's group ID, avoid generating different values by hostname or pod name.

Do not multiply concurrency mechanically. For example, six replicas with concurrency four create up to 24 consumer members. If the topic only has eight partitions, most members will have no partitions. Moreover, many consumers increase connection counts, fetch requests, threads, and database pressure. Choose replica counts and concurrency based on partition count and target throughput.

## 6. Kafka Distributes Partitions Among Members

When a consumer starts, it registers to join the group and declares its subscription. The group coordinator manages membership; the group leader executes the assignment according to a partition assignment strategy supported by the members. The assignment defines which consumer owns which partition.

Common distribution strategies include:

| Strategy | General characteristics |
|---|---|
| `RangeAssignor` | Distributes partitions by range within each topic; across multiple topics, load between consumers may be uneven. |
| `RoundRobinAssignor` | Distributes partitions in round-robin order across consumers, often producing a more even spread when subscriptions match. |
| `StickyAssignor` | Attempts balanced distribution while retaining as many previous assignments as possible. |
| `CooperativeStickyAssignor` | Combines sticky goals with incremental cooperative rebalancing to reduce how many partitions must be revoked at once. |

Do not rely on a fixed assignment order in business logic. Partitions can move to other members when the group changes. The application must work properly regardless of which replica processes a partition.

With cooperative rebalancing, assignment transfers can happen across multiple steps, revoking only the partitions that need to move. This mechanism reduces processing pauses in many situations, though it requires compatible members and configuration. Check your Kafka client version and active strategies before changing assignor settings.

## 7. Rebalances When Instances Join or Leave the Group

The group must redistribute partitions when membership or subscriptions change. Common situations include:

- A new replica starts up and joins the group.
- A replica stops cleanly or is replaced during deployment.
- A consumer fails to send heartbeats on time or exceeds the poll progress limit.
- Topic subscriptions or partition counts change.
- A member experiences network errors or its process terminates abruptly.

Example of a group with two members:

```text
Before scaling:
  Consumer A -> P0, P1, P2
  Consumer B -> P3, P4, P5

Consumer C joins the group
          |
          v
      Rebalance
          |
          v
After scaling:
  Consumer A -> P0, P1
  Consumer B -> P2, P3
  Consumer C -> P4, P5
```

The post-rebalance assignment is illustrative only. Kafka may produce a different distribution depending on the assignor and group state.

During a rebalance, partitions may temporarily pause processing as ownership transfers. Old consumers must complete revocation steps per the protocol, while new consumers receive assignments and begin reading from the group's committed offsets. If the application frequently adds or removes replicas in short succession, continuous rebalances can degrade throughput and increase lag.

When scaling deployments, configure appropriate rollout policies to avoid stopping too many replicas at once. Graceful shutdown allows the listener container to stop accepting new work, complete or handle in-flight work within the allowed timeout, and leave the group cleanly. On abrupt shutdowns, the group must detect the disconnected member and redistribute partitions after timeouts expire.

## 8. Offsets Are Stored per Group and Partition

Committed offsets belong to a consumer group and partition pair. When one member leaves the group, another member assigned that partition resumes from the existing committed offset.

Example:

```text
Group: order-service
Partition: orders-2
Committed offset: 120

Consumer A processes record 120
Consumer A stops before committing 121
          |
          v
Rebalance assigns orders-2 to Consumer B
          |
          v
Consumer B resumes from offset 120
```

Record 120 may be processed again. If A already produced an external business effect without committing, B may repeat that effect. Therefore, listeners must handle repeated processing safely—such as using the event ID as an idempotency key or recording a processed marker within the same transaction as the business change.

If A commits offset 121 before business work completes, B may start at 121 and record 120 is skipped according to stored progress. Therefore, acknowledge offsets only after required work completes. For logic writing to external databases outside Kafka, Kafka offset commits and database transactions do not automatically form an atomic transaction.

Each group maintains its own progress. If a new group ID is created, that group has no prior committed offsets and applies `auto.offset.reset` when starting to read. With `earliest`, the new group may re-read from the earliest retained offset; with `latest`, the group starts at the end of the log at the time offsets are resolved. Consequently, changing a group ID during deployment can make a service re-read a large volume of data or skip older data depending on configuration.

## 9. Static Membership and Consumer Identity

Kafka supports static membership via `group.instance.id`. This property provides a stable identifier for a member so the group can recognize it when it restarts under certain conditions. Static membership can reduce rebalances from brief restarts, particularly in deployment environments with stable instance identities.

`group.instance.id` must be unique within a group. Do not assign the same value to all replicas, because two consumers sharing a static member ID can be treated as a conflict and one member may be fenced from the group. When using Spring Kafka with concurrency greater than one, each consumer member also needs a distinct static identity if static membership is configured; follow how your Spring Kafka version generates or appends IDs for child containers.

Static membership does not replace heartbeats or the poll loop, nor does it allow consumers to stall indefinitely. It changes how the group handles temporary member disconnects; detecting permanently lost members may be delayed according to timeouts. Enable it only when there is a clear need, stable unique identities exist, and replacement timeout impacts are understood.

`client.id` is a different property, commonly used to identify clients in logs, metrics, and quotas. `group.id` defines the logical consumption group; `group.instance.id` identifies a static member within the group; `client.id` aids client observability. Do not use these three values interchangeably.

## 10. Multi-Replica Deployment Example

Suppose the `order-service` reads topic `orders` with six partitions. The goal is to run three replicas, each using one consumer for the listener.

```yaml
spring:
  kafka:
    bootstrap-servers: kafka:9092
    consumer:
      group-id: order-service
      enable-auto-commit: false
      auto-offset-reset: earliest
    listener:
      concurrency: 1
      ack-mode: record
```

Listener:

```java
@KafkaListener(topics = "orders")
public void consume(ConsumerRecord<String, OrderCreated> record) {
    orderService.handle(record.value());

    log.info(
        "Handled order event: topic={}, partition={}, offset={}, key={}",
        record.topic(),
        record.partition(),
        record.offset(),
        record.key()
    );
}
```

When deploying three replicas with the same configuration, Kafka creates three consumer members in group `order-service`. With six partitions, each member can receive two partitions. When scaling replicas to six, the group can assign one partition per member. When scaling down to two replicas, each member can receive roughly three partitions.

If two consumers per replica are needed, set `concurrency: 2`. With three replicas, the group has up to six consumer members. Ensure the partition count is sufficient to use that parallelism and the backing database can handle the increased processing threads.

In Kubernetes, the Deployment's `replicas` setting determines the number of application processes, while `concurrency` determines the number of consumers per process for that listener. Multiply these two values to estimate the member count. During a rollout, Kubernetes may create new pods before old pods terminate; during that window, member count can temporarily exceed desired replicas and trigger rebalances. Coordinate `maxSurge`, `maxUnavailable`, readiness probes, and graceful shutdown with service availability requirements.

## 11. Common Mistakes When Running Multiple Instances

| Symptom | Possible cause | Resolution |
|---|---|---|
| Every replica processes the exact same event | Each replica uses a different group ID. | Use the same stable group ID for replicas that need to share load. |
| Some replicas receive no records | More consumer members than partitions or unexpected assignment distribution. | Check partition count, group assignments, and concurrency. |
| Two services both need events, yet only one receives them | Both services share the same group ID. | Create a separate group ID for each logical processing unit needing independent progress. |
| Increasing replicas does not raise throughput | Insufficient partitions, skewed partitions, or saturated dependencies. | Measure assignments, per-partition lag, listener duration, and database load. |
| Duplicate processing appears after deployment | Rebalance occurred after record processing but before offset commit. | Use idempotency and acknowledge offsets after business work completes. |
| Rebalances happen continuously | Replicas restarting frequently, heartbeat/poll timeouts, or rapid membership churn during rollouts. | Inspect group logs, timeouts, poll loop, and rollout strategy. |
| One partition becomes a bottleneck | Uneven key distribution or one partition holding substantially more data. | Inspect key distribution and per-partition lag; adjust partitioning strategy if appropriate. |

When investigating, inspect group state and per-member assignments rather than looking only at total running replicas. A pod showing healthy in Kubernetes does not guarantee it has partitions assigned; a member may be idle because there are more consumers than partitions.

## 12. Operational Principles

- Use the same stable `group.id` across replicas that need to share load in the same consumer group.
- Use separate group IDs for each logical service that needs to read all events independently.
- Design partition counts based on required parallelism and downstream system capacity.
- Calculate total consumer members as replica count multiplied by listener concurrency; check partition counts before raising concurrency.
- Never assume a partition will always stay assigned to the same instance. Applications must handle partitions moving to other members.
- Monitor assignments, per-partition lag, rebalances, processing durations, and commit rates.
- Design idempotent business logic to tolerate records redelivered after rebalances or failures.
- Use graceful shutdown and controlled rollouts to minimize unnecessary rebalances.
- Use static membership only when stable, unique identities exist for every consumer member and timeout impacts are understood.

Multiple instances in the same consumer group increase parallel processing capacity and preserve service availability when a replica leaves. Scaling effectiveness depends on partition counts, key distribution, Spring Kafka concurrency, and backing system capacity. When group IDs are configured properly and partition reassignments are handled safely, replicas collaborate to share load while keeping consumption progress independent from other consumer groups.

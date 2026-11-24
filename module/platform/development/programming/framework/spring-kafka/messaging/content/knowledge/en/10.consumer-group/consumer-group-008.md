# Choosing group.id for Each Use Case

In Kafka, **`group.id`** identifies the consumer group a consumer joins. The group ID determines which other consumers a consumer shares partitions with and which group Kafka stores reading progress (offsets) for. Therefore, choosing `group.id` is a decision about how a use case consumes events, not simply naming an application instance.

If multiple replicas of the same function need to share processing load, they normally share the same `group.id`. If multiple systems each need to independently receive all events from a topic, each system needs its own `group.id` to maintain independent offsets and reading progress. Misconfiguring `group.id` can cause consumers to accidentally split records among themselves or redundantly reprocess the entire event stream and produce duplicate business side effects.

This lesson belongs to the **Consumer group** chapter of the **SPRING_KAFKA_MESSAGING** module, focusing on how to choose `group.id` per use case, how Spring Kafka configures groups for listeners, and how to manage reading progress when running multiple replicas, multiple applications, or replaying data.

## Learning Outcomes

After this lesson, you can:

- Explain how `group.id` links consumers with membership and offsets.
- Distinguish multiple replicas of the same use case from multiple independent consuming use cases.
- Choose appropriate `group.id` values for order processing, analytics, audit, and other consumers.
- Configure a default group in Spring Boot and override the group per `@KafkaListener`.
- Understand the impact of changing `group.id` on offsets, replay, and business side effects.
- Isolate groups by environment when multiple environments share a Kafka cluster.
- Design stable, observable, conflict-free group IDs.
- Plan safe blue-green deployments, shadow consumers, and group migrations.

## 1. group.id Is the Identifier of a Consumer Group

Kafka uses `group.id` to identify a set of consumers coordinating to read data. Consumers with the same `group.id` belong to the same logical group. The Kafka group coordinator manages membership, distributes partitions, and coordinates offset storage for the group.

Offsets are stored per group, topic, and partition. You can picture reading progress as a set of positions, each tied to a partition within a specific group. When a consumer commits an offset, that progress belongs to the `group.id` in use.

For example, an `orders.created` topic with three partitions:

~~~mermaid
flowchart LR
    T[Topic: orders.created] --> P0[Partition 0]
    T --> P1[Partition 1]
    T --> P2[Partition 2]
    subgraph G1["Group: orders-fulfillment"]
        C1[Consumer A]
        C2[Consumer B]
    end
    P0 --> C1
    P1 --> C1
    P2 --> C2
    subgraph G2["Group: orders-analytics"]
        A1[Analytics consumer]
    end
    P0 --> A1
    P1 --> A1
    P2 --> A1
~~~

In the example:

- `orders-fulfillment` is one group whose consumer members divide the three partitions.
- `orders-analytics` is another group with its own reading progress and can read every record in the topic.
- The two groups do not share offsets. When the fulfillment group commits offsets, it does not cause analytics to skip records.

Whether a new group reads all retained history or only new records depends on existing offsets and `auto.offset.reset`. Independent groups have separate progress, but each group's starting point must still be configured intentionally.

This is the core rule when designing `group.id`: same group to share the load of one processing stream; different groups to consume independently.

## 2. Sharing group.id Across Replicas of the Same Use Case

Suppose the fulfillment service runs three replicas performing the same `OrderCreatedEvent` processing function. All three replicas should use the same `group.id`, such as `orders-fulfillment`.

Kafka will distribute the topic's partitions across the consumer members in the group. Each record is delivered to one member according to the current assignment, allowing replicas to share processing load.

~~~mermaid
flowchart TB
    T[orders.created: 6 partitions]
    T --> P[Partition assignment]
    P --> C1[fulfillment instance 1]
    P --> C2[fulfillment instance 2]
    P --> C3[fulfillment instance 3]
    C1 -.-> G["Shared group.id: orders-fulfillment"]
    C2 -.-> G
    C3 -.-> G
~~~

Example Spring Boot configuration:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-fulfillment
      enable-auto-commit: false
~~~

Replicas of the same deployment receive the same configuration. When one replica stops, Kafka can rebalance and assign that replica's partitions to the remaining members. When a new replica joins, the group redistributes partitions again.

A partition being assigned to only one member at a time does not equate to exactly-once processing. If a consumer processes a record but stops before its offset is committed, the record can be redelivered after a rebalance. Business logic should safely handle duplicate deliveries, such as using `eventId` as an idempotency key.

Do not include hostnames, pod names, UUIDs, or instance IDs in `group.id` if the goal is for replicas to share load. If each replica has its own `group.id`, each replica becomes an independent group and can receive all records in the topic, multiplying processing.

## 3. Using a Separate group.id for Each Independent Use Case

A single topic can supply events to multiple business functions. For example, `OrderCreatedEvent` is used by fulfillment to reserve inventory, analytics to aggregate metrics, and audit to record activity trails.

If each use case needs to receive all records independently, each use case needs its own `group.id`:

| Use case | Suggested Group ID | Purpose |
|---|---|---|
| Fulfillment | orders-fulfillment | Handle stock reservation and order fulfillment. |
| Analytics | orders-analytics | Aggregate metrics and generate reports. |
| Audit | orders-audit | Persist event trails for auditing. |
| Notification | orders-notification | Send notifications on order events. |

Consumers within the same group share partitions. Different groups can read the entire topic stream together, each with its own offsets.

Example of two listeners belonging to two independent use cases:

~~~java
@Component
public class OrderAnalyticsListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-analytics"
    )
    public void onOrderCreated(OrderCreatedEvent event) {
        // Update analytics data.
    }
}
~~~

~~~java
@Component
public class OrderAuditListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-audit"
    )
    public void onOrderCreated(OrderCreatedEvent event) {
        // Store audit trail.
    }
}
~~~

These two listeners have different group IDs, so each use case maintains its own reading progress. If audit pauses temporarily, analytics continues reading and committing offsets for the analytics group.

Do not create separate groups per method or per request if the consumers are actually replicas of the same use case. Place group boundaries along the reading progress and processing responsibilities you want to manage independently.

## 4. How Do Same Topic + Different Groups vs. Same Group Differ?

These two patterns behave very differently:

| Organization | How Kafka distributes records | When to use |
|---|---|---|
| Multiple consumers with same `group.id` | Consumers divide partitions; a partition is assigned to one member at a time | Multiple replicas executing the same use case to share load. |
| Multiple consumers with different `group.id` | Each group maintains its own offsets and consumes independently; start point depends on offsets and `auto.offset.reset` | Multiple use cases needing to receive the same events. |

For example, three fulfillment instances in group `orders-fulfillment` share processing load. An analytics consumer using group `orders-analytics` still reads those records at its own pace. Whether it receives retained history or only new records depends on the initial offset configuration of the analytics group.

A common configuration mistake is using the same `group.id` for analytics and fulfillment simply because both listeners read `orders.created`. In that case, the two functions split partitions and each function receives only a subset of events. Consequently, analytics misses orders received by fulfillment, or vice versa.

Conversely, if three fulfillment replicas accidentally use three different group IDs, each replica can receive every order and reserve stock three times. This error can cause serious business impact.

## 5. Configuring the Default Group in Spring Boot

Spring Boot lets you declare a default group ID via `spring.kafka.consumer.group-id`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-fulfillment
      auto-offset-reset: earliest
      enable-auto-commit: false
~~~

Listeners that do not declare a specific group can use the group ID from the consumer factory configuration. This fits applications that primarily serve a single event-consuming use case.

When an application has multiple listeners belonging to different use cases, configure the group explicitly on each listener with `groupId`. This clarifies intent and prevents listeners from accidentally sharing the default group.

Example with a default configuration for fulfillment while the analytics listener uses its own group:

~~~java
@Component
public class OrderListeners {

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-fulfillment"
    )
    public void fulfill(OrderCreatedEvent event) {
        // Process order.
    }

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-analytics"
    )
    public void analyze(OrderCreatedEvent event) {
        // Analyze event.
    }
}
~~~

In this example, `groupId` on `@KafkaListener` specifies the group for that respective listener and overrides the default group from the consumer factory. Verify the actual configuration of each listener when an application has multiple containers.

## 6. Naming group.id by Use Case

A group ID should be stable, meaningful, and reflect its processing responsibility. A simple convention:

~~~text
<domain>-<use-case>-<environment>
~~~

Examples:

~~~text
orders-fulfillment-prod
orders-analytics-prod
orders-audit-prod
payments-reconciliation-staging
inventory-reservation-dev
~~~

Meaningful components:

- **domain:** business domain or data category, such as `orders`, `payments`, `inventory`.
- **use-case:** consuming function, such as `fulfillment`, `analytics`, `audit`, `reconciliation`.
- **environment:** deployment environment when environments may share a cluster or need separated progress.

A few guidelines:

- Use names that stay stable across restarts and replica scaling.
- Avoid putting pod names, hostnames, or UUIDs into the group ID of load-sharing consumers.
- Assign distinct group IDs to use cases with independent progress and responsibilities.
- Add a version suffix only when you genuinely want to create a new reading progress or run a new consumer contract in parallel.
- Keep naming consistent so group lag, offsets, and membership are easy to look up.
- Do not embed secrets or personal data in group IDs.

There is no single mandatory naming pattern for every system. What matters is that the group ID reflects the processing boundary and is managed as part of operational configuration.

## 7. Separating group.id by Environment

If development, staging, and production connect to the same Kafka cluster, do not let all consumers use the same group ID. If they share a group, consumers in one environment can receive partitions instead of consumers in another environment and alter shared reading progress.

Example:

| Environment | Group ID |
|---|---|
| Local | orders-fulfillment-local |
| Development | orders-fulfillment-dev |
| Staging | orders-fulfillment-staging |
| Production | orders-fulfillment-prod |

If each environment has its own Kafka cluster, including the environment name in the group ID can still help consistency and observability, even though the group namespace is already separated by cluster.

Example using Spring profiles:

~~~yaml
# application-local.yml
spring:
  kafka:
    consumer:
      group-id: orders-fulfillment-local
~~~

~~~yaml
# application-prod.yml
spring:
  kafka:
    consumer:
      group-id: orders-fulfillment-prod
~~~

When running the application, confirm the active profile and effective group ID. A local configuration accidentally pointed at a production cluster can create an unintended consumer group and affect live data.

## 8. Changing group.id Can Change the Starting Read Position

Offsets are stored per group. When you change `group.id`, the consumer joins a different group and does not use the old group's committed offsets.

If the new group does not yet have valid offsets, `auto.offset.reset` determines the starting position:

- **earliest:** starts from the earliest offset still retained in the log.
- **latest:** starts from new records arriving once the consumer begins reading.
- **none:** throws an error if no valid offset is found according to client configuration.

`auto.offset.reset` only takes effect when a group has no valid offset. It does not overwrite committed offsets of an existing group and is not a tool to rewind data on every restart.

Example old group:

~~~text
orders-fulfillment
partition 0 committed offset = 120
partition 1 committed offset = 95
~~~

If the group ID is changed to `orders-fulfillment-v2`, the new group does not yet have its own offsets. With `auto.offset.reset=earliest`, it can start from the earliest retained offset. Previously processed records may be read again, causing duplicate business effects if the consumer is not idempotent.

Changing `group.id` does not delete the old group's offsets. Old offsets remain according to Kafka's offset retention policy until they expire or are deleted via administration procedures.

Before changing `group.id`, clarify whether the goal is to start fresh progress, replay data, or merely rename. If you only want to rename while continuing from old offsets, prepare a proper offset-migration plan and test thoroughly before deploying.

## 9. Using a Separate Group for Replay or Shadow Consumers

A separate group ID is useful when you need to re-read data or test new consumer logic without altering the progress of the active production group.

Example replay group:

~~~text
orders-fulfillment-replay-2026-11
~~~

With a new group and `auto.offset.reset=earliest`, the consumer can re-read records still retained in the topic. This is a helpful way to rebuild analytics data or validate a new processing version.

However, replaying can re-trigger external side effects such as reserving stock, charging money, or sending notifications. Before replaying, you must:

1. Identify the data range and topics to read.
2. Use a separate group ID so production offsets are unaffected.
3. Determine `auto.offset.reset` and specific seek/offset policies.
4. Control business side effects; prefer a separate environment or output if only validating.
5. Ensure consumers are idempotent if events might be reprocessed.
6. Monitor lag and replay speed so downstream systems are not hit by a sudden load spike.
7. Record results and stop the replay group once finished.

For a shadow consumer, the new group reads the same stream but only observes or writes results to a test destination. Do not let a shadow consumer trigger production business side effects without deduplication design and deployment approval.

## 10. Blue-Green Deployment and Group Migration

When deploying a new version, you must decide whether the new consumers will join the old group or a new group.

**Using the same group ID:** old and new versions share partitions. This is the common choice for rolling deployments that continue a single shared reading progress. However, the two versions must be compatible in schema, event handling, and offset commit behavior. While both versions run together, partitions can be distributed across them.

**Using a new group ID:** the new version creates independent reading progress and can re-read data per `auto.offset.reset`. This helps for shadow testing or migrations requiring side-by-side comparison, but risks reprocessing all data and producing duplicate side effects.

A migration plan should define:

- Whether the new version is event-schema compatible with current producers.
- Whether two groups will run concurrently during the cutover window.
- Where the new group's offsets will start.
- Whether the new consumer is permitted to produce production side effects.
- When to stop the old group and how to roll back if errors are detected.
- How to monitor lag, errors, and output discrepancies between the two versions.

Do not append a `v2` suffix to the group ID merely because an application name or software version changed. Use a new group ID only when you genuinely need independent reading progress.

## 11. How Does group.id Differ from client.id and Listener ID?

IDs in Kafka/Spring Kafka serve distinct roles:

| ID | Role |
|---|---|
| `group.id` | Identifies the consumer group and the group's offset namespace. |
| `client.id` | Identifies the client to support Kafka-side logs, metrics, and quotas. |
| `member.id` | Identifies a member within a consumer group managed by Kafka. |
| `@KafkaListener id` | Identifies the listener container within the Spring Kafka application. |

Do not use `client.id` instead of `group.id`. Multiple consumers can have different `client.id` values and still belong to the same group if they share `group.id`. Conversely, two consumers with the same `client.id` but different `group.id` values still belong to two independent groups.

Spring Kafka also provides settings to generate client IDs per consumer thread/container. Client IDs help observe individual instances; group IDs govern load sharing and reading progress. Keep the two concepts separate when designing configurations and dashboards.

## 12. Common Mistakes When Choosing group.id

| Configuration Mistake | Consequence | Fix |
|---|---|---|
| Each replica uses a different group ID | Each replica reads the entire stream, causing potential duplicate processing | Share the same `group.id` across replicas of the same use case. |
| Multiple independent use cases share one group | Use cases split records and each receives only a subset | Separate group IDs for each use case needing independent reads. |
| Dev and production share a group on one cluster | Consumers from both environments compete for partitions and share offsets | Separate group IDs by environment. |
| Changing group ID without evaluating offsets | New consumer may replay data or skip old data depending on `auto.offset.reset` | Plan offset transitions and test before changing. |
| Generating a random group ID on each run | Each restart may start fresh progress and re-read data | Use a stable group ID. |
| Using a new group for a shadow consumer with side effects enabled | Events may trigger business actions twice | Use observation-only mode or separate outputs, and enforce idempotency. |
| Using `client.id` as `group.id` | Confusing client identity with consumer progress | Configure `group.id` and `client.id` separately. |

An important warning sign to watch for is an unusually rising number of consumer groups or many groups serving the same purpose. This can indicate an application unintentionally generating dynamic group IDs.

## 13. Testing group.id Configuration

Testing group IDs should verify group behavior rather than merely reading values from `application.yml`.

Recommended scenarios:

- Multiple replicas with the same group ID share partitions.
- Two different group IDs both read all records from the topic.
- Two listeners with the same group ID intentionally sharing load.
- Listeners belonging to two different use cases using separate group IDs.
- A new group starting from `auto.offset.reset` when no offsets exist yet.
- An existing group resuming from committed offsets after restart.
- Changing group ID leaving the old group's offsets untouched.
- Local and production environments not accidentally sharing a group on the same cluster.

You can use EmbeddedKafka or Testcontainers to spin up multi-partition topics and verify how records are distributed across groups. For group assignment tests, wait on assignment events or explicit conditions with timeouts; do not use fixed `Thread.sleep` durations to guess that a group has stabilized.

When testing `auto.offset.reset`, create a new group or delete test offsets in a controlled way. If a group already has valid offsets, `earliest` will not rewind the consumer to the beginning of the topic. This is a common reason replay tests do not produce expected results.

## 14. Capstone Exercise: Designing Groups for an Order System

Suppose producers emit events to the `orders.created` topic. The system has three functions: fulfillment, analytics, and audit. Each function can run multiple replicas.

Requirements:

1. Choose separate group IDs for fulfillment, analytics, and audit.
2. Run two fulfillment replicas with the same group ID and observe them sharing partitions.
3. Run analytics and audit with their own group IDs, verifying each group receives the full stream.
4. Stop one fulfillment replica and observe the rebalance.
5. Create a new replay group with `auto.offset.reset=earliest` to re-read retained data.
6. Verify the replay group does not change production fulfillment offsets.
7. Run local and staging against the same cluster using different group IDs.
8. Test the misconfiguration: three fulfillment replicas using three different group IDs; observe how many records each replica receives.
9. Test the misconfiguration: analytics sharing a group with fulfillment; observe the two use cases splitting partitions.
10. Build a shadow consumer using a separate group without triggering production side effects.
11. Log group ID, client ID, topic, partition, and offset to aid traceability.
12. Write integration tests verifying load-sharing and independent-reading behaviors.

The deliverable should include an ownership table:

| Group ID | Use case | Expected Replicas | Topic subscription | Side effects |
|---|---|---:|---|---|
| orders-fulfillment-prod | Order fulfillment | 2+ | orders.created | Reserve stock, update order |
| orders-analytics-prod | Analytics | 1+ | orders.created | Write analytics data |
| orders-audit-prod | Audit | 1+ | orders.created | Persist audit trail |
| orders-replay-test | Test replay | As needed | orders.created | No production side effects |

Document the owner, environment, purpose, and offset policy for each group. This helps operations teams know which groups are allowed to replay, which produce side effects, and which exist strictly for observation.

## 15. Learning Sequence and Completion Criteria

| Stage | Core Focus | Self-Check Criterion |
|---|---|---|
| 1. Group identity | `group.id` and consumer groups | Can explain how group ID ties to membership and offsets. |
| 2. Scale replicas | Multiple instances in one group | Replicas share partitions to process one use case. |
| 3. Independent use cases | Multiple groups on one topic | Each use case receives all records with its own offsets. |
| 4. Spring Kafka | `consumer.group-id` and `@KafkaListener` `groupId` | Properly configures default groups and per-listener groups. |
| 5. Environment | Local, dev, staging, production | Prevents environments from unintentionally sharing groups. |
| 6. Offset/replay | `auto.offset.reset` and new groups | Can predict starting position when a group has no offsets yet. |
| 7. Migration | Blue-green and shadow consumers | Can choose between reusing the old group or creating a new group per goal. |
| 8. Operations | Naming, ownership, metrics | Can look up the owner, purpose, and progress of every group. |
| 9. Testing | EmbeddedKafka/Testcontainers | Can verify load-sharing and independent reads. |

The lesson is complete when you can design group IDs by use case, configure them accurately in Spring Kafka, explain the impact of group IDs on partition assignments and offsets, and plan replays or migrations without causing unintended duplicate processing.

A helpful design rule is: replicas performing the same processing stream share a group ID; use cases that need independent reads use separate group IDs. When you treat `group.id` as part of your operational contract, you gain better control over load sharing, replays, multi-environment deployments, and consumer traceability in Spring Kafka systems.


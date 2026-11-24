# group.id and consumer group naming

## 1. What is group.id?

In Kafka, `group.id` is the identifier of a consumer group. Consumers with the same `group.id` join the same group, coordinate reading topics, and divide the assigned partitions among themselves. Kafka uses this identifier to manage group membership, distribute partitions, and store reading progress.

In a Spring Kafka application, `group.id` is usually declared via Spring Boot consumer configuration or set individually on each `@KafkaListener`. This is one of the most important configurations when deploying a consumer because it determines which subscription the consumer belongs to and from which progress position it will resume reading.

For example, three instances of an order-processing service share `group.id=orders-processor-prod`. Kafka treats them as three members of one group and divides partitions among them. If a fraud-checking service also needs to receive all order events, that service needs a separate group ID, such as `fraud-monitor-prod`.

## 2. How does group.id relate to topics, partitions, and offsets?

A topic can be subscribed to by multiple consumer groups. Within each group, each partition is assigned to at most one consumer at a time. Therefore, consumers in the same group share the workload; different groups can independently read the same event stream.

~~~mermaid
flowchart TB
    T["Topic orders<br/>P0 · P1 · P2 · P3"]
    T --> G1["Group: orders-processor"]
    T --> G2["Group: fraud-monitor"]
    G1 --> A["Consumer A<br/>P0, P1"]
    G1 --> B["Consumer B<br/>P2, P3"]
    G2 --> C["Consumer C<br/>P0, P1"]
    G2 --> D["Consumer D<br/>P2, P3"]
~~~

In the diagram:

- `orders-processor` has two consumers sharing four partitions. Each record belonging to a partition is received by one member of the group.
- `fraud-monitor` has its own reading progress and can also read all events in the `orders` topic.
- The same record can be read by both groups, while each group manages its own offsets independently.

Kafka stores committed offsets per combination of group ID, topic, and partition. Consequently, the `orders-processor` group may have read up to offset 120 of partition P0, while `fraud-monitor` is still at offset 75 of the same partition. One group reading a record does not remove the record from the topic and does not alter another group's offset.

Consumer group offsets are stored by Kafka in the internal `__consumer_offsets` topic. When a consumer restarts or a partition is reassigned to another consumer, the group can resume from the most recently committed offset.

Kafka selects one broker as the group coordinator for each consumer group. The coordinator manages membership, heartbeats, and the partition distribution process. When a consumer joins or leaves the group, a heartbeat expires, the subscription changes, or the partition count changes, Kafka may perform a rebalance to recalculate assignments. During a rebalance, consumption may pause temporarily.

## 3. Declaring group.id in Spring Boot

A common approach is declaring the default group ID in `application.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-processor
      auto-offset-reset: earliest
      enable-auto-commit: false
~~~

With the configuration above, listeners that do not specify a dedicated group ID will use the default `orders-processor` group from the consumer configuration.

Example of a listener receiving order events:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @KafkaListener(topics = "orders")
    public void handle(OrderCreatedEvent event) {
        // Process order created event.
    }
}
~~~

When the application runs multiple instances, each instance of the same service uses the shared configuration and group ID. Kafka places those consumers into the same group to divide partitions.

### Assigning a dedicated group ID per listener

If an application has multiple listeners serving different business workflows, you can specify `groupId` directly on `@KafkaListener`:

~~~java
@Component
public class FraudDetectionListener {

    @KafkaListener(
        topics = "orders",
        groupId = "fraud-monitor"
    )
    public void inspect(OrderCreatedEvent event) {
        // Check for signs of fraud.
    }
}
~~~

The `groupId` attribute on `@KafkaListener` overrides the default group ID in consumer configuration for that listener. This example allows `FraudDetectionListener` to receive the `orders` stream independently of the listener using the `orders-processor` group.

Placeholders can be used to manage group names in configuration:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-processor
~~~

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "${spring.kafka.consumer.group-id}"
)
public void handle(OrderCreatedEvent event) {
    // Process event.
}
~~~

Using centralized configuration makes it possible to change group names per environment without modifying source code.

## 4. How should consumer groups be named?

A group name should describe the service or business workflow consuming events. An easy-to-manage convention combines the capability name, environment, and version when needed:

~~~text
<service>-<purpose>-<environment>[-v<version>]
~~~

Example:

| Group ID | Purpose |
|---|---|
| `orders-processor-dev` | Order processing in the development environment |
| `orders-processor-prod` | Order processing in the production environment |
| `fraud-monitor-prod` | Fraud analysis in production |
| `billing-service-prod` | Processing events for billing |
| `orders-processor-prod-v2` | New consumer with reading progress independent of the previous version |

Several naming principles:

- **Stable:** deployments of the same logical consumer typically reuse the same group ID to continue from committed offsets.
- **Environment-distinct:** dev, test, staging, and production should have separate group IDs if connecting to the same Kafka cluster, preventing test consumers from joining the production group.
- **Workflow-distinct:** two services that each need to receive the entire set of the same events must have different group IDs.
- **Intentional versioning:** adding a version suffix creates a new group with separate reading progress. Only do this when you truly want an independent subscription, such as running a new consumer in parallel to validate or replay data.
- **Same name across replicas:** pods or instances running the same logical consumer must share the same group ID to divide load.

Do not generate random group IDs or attach a pod ID to the group ID on each startup if the goal is horizontally scaling a service. When each pod uses a different group ID, Kafka treats each pod as an independent subscriber; all of them may read the entire topic at their own offsets, multiplying processing count and system load.

## 5. What happens when group.id is changed?

A group ID is not just a display name. It is part of the key identifying consumption progress. When you change the group ID, Kafka treats the consumer as a new group if that name has no existing state.

Suppose `orders-processor-prod` has committed up to offset 500 of partition P0. If the application is deployed with a new group ID `orders-processor-prod-v2`, the new group has no committed offset yet. In that case, `auto.offset.reset` determines the starting position:

| Configuration | Behavior when group has no valid offset |
|---|---|
| `earliest` | Starts from the oldest record still retained in the partition |
| `latest` | Starts at the end of the log at the time the read position is initialized; normally only receives records written afterward |
| `none` | Throws an error if no valid offset is found |

`auto.offset.reset` does not overwrite valid committed offsets. If a group already has an offset, the consumer resumes from that progress. With `earliest`, Kafka can also only read records still within the retention period; data already deleted by retention cannot be recovered by changing configuration.

Before changing a group ID, clarify the goal:

- If merely deploying additional replicas to increase throughput, keep the same group ID.
- If replacing an application version while wanting to continue current progress, reuse the current group ID and control the rollout process.
- If wanting a new consumer to read independently or replay data, create a new group ID and choose the appropriate `auto.offset.reset`.
- If the old group is no longer used, consider offset cleanup and related data policies according to the Kafka cluster's operational procedures.

Changing a group ID can cause business logic to reprocess many events or skip history, depending on offsets and `auto.offset.reset`. Consumers should still support idempotent processing because retries, rebalances, and failures after processing but before committing can lead to redelivered records.

## 6. Distinguishing group.id from client.id and listener id

These identifiers serve different purposes:

| Property | Purpose | Usage Scope |
|---|---|---|
| `group.id` | Identifies the consumer group and shared reading progress | Consumers collaborating to divide partitions |
| `client.id` | Identifies a Kafka client for logs, metrics, and observability | Per consumer/producer client |
| `@KafkaListener(id = "...")` | Identifies a listener container in Spring Kafka | Managing listener containers inside the application |
| `group.instance.id` | Stably identifies a member when using static membership | Per consumer instance within a group |

Do not use `client.id` in place of `group.id`. Two consumers with different `client.id` values still belong to the same group if they use the same `group.id`. Conversely, consumers with the same `client.id` but different group IDs belong to different groups.

`@KafkaListener` has an `id` attribute to identify the container. In common Spring Kafka configurations, if only `id` is set without `groupId`, that ID may be used as the group ID by default via `idIsGroup`. To avoid confusion between container identification and consumer group identification, explicitly declare `groupId` when controlling subscriptions.

`group.instance.id` is an advanced option for static membership. Each consumer instance in the same group must have a distinct value that remains stable across the instance lifecycle. Do not assign the same `group.instance.id` to all replicas. This property does not replace `group.id`; it only helps Kafka recognize a specific member and can reduce unnecessary rebalances when a member temporarily disconnects within configured limits.
## 7. Common configuration errors

### Each replica uses a different group ID

**Symptom:** every replica reads nearly all events, causing processing volume to multiply by the number of replicas.

**Cause:** the group ID is dynamically generated, containing a pod ID or random string.

**Fix:** configure a stable group ID for the same logical consumer. Let Kafka distribute partitions across replicas.

### Two independent services share the same group ID

**Symptom:** service A receives part of the records and service B receives the rest; neither service sees all expected events.

**Cause:** two services that need independent processing share the same group ID, so Kafka treats them as competing members in the same group.

**Fix:** assign a separate group ID to each business workflow that needs to receive the full event stream.

### Unintended group ID change

**Symptom:** the consumer re-reads a large amount of old data or skips history.

**Cause:** the group name changed, causing Kafka to find no committed offset for the new group and apply `auto.offset.reset`.

**Fix:** keep group names stable across deployments; change them only when there is a clear plan for new reading progress.

### Increasing consumers while partition count stays unchanged

**Symptom:** some consumers remain in an unassigned state with no partitions and process no records.

**Cause:** the number of consumers in the group exceeds the number of partitions available to distribute.

**Fix:** evaluate partition count and concurrency against target throughput. A partition is assigned to at most one consumer in the same group at any given time.

### Mixing up group IDs across environments

**Symptom:** test consumers join the same group as the production application or alter shared reading progress.

**Cause:** environments share the same cluster while configuring identical group IDs.

**Fix:** include the environment name in the group ID and verify profile-specific configuration before deployment.

## 8. Monitoring and inspecting consumer groups

In operations, monitor group membership, partition assignment, committed offsets, and consumer lag. Consumer lag represents the gap between the end of the log and the consumer's committed progress; sustained growing lag can signal slow consumer processing, too few consumers, or connectivity issues.

You can use Kafka CLI to list groups in the cluster:

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list
~~~

View members, partition assignments, offsets, and lag of a group:

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group orders-processor-prod
~~~

Script names may differ depending on the Kafka installation or operating system. When running on Windows, use the corresponding `.bat` scripts in the `bin/windows` directory.

When investigating a consumer not receiving records, check in order:

1. Is the consumer connecting to the right cluster and subscribing to the right topic?
2. What is the listener's actual `group.id`? Is `@KafkaListener(groupId=...)` overriding the default configuration?
3. Does the group have active members and have partitions been assigned?
4. Where are the committed offsets? Was `auto.offset.reset` applied because the group had no valid offset?
5. Is consumer lag increasing? Are there deserialization, processing, or rebalance errors in the logs?

## 9. group.id selection checklist

- [ ] Multiple replicas of the same workflow share a stable group ID.
- [ ] Each workflow needing the full event stream has its own group ID.
- [ ] Group names distinguish environments when environments share a Kafka cluster.
- [ ] Pod IDs or random strings are not embedded in group IDs when load sharing is intended.
- [ ] It is clearly understood that changing a group ID creates independent consumption progress.
- [ ] `auto.offset.reset` is chosen intentionally for new groups.
- [ ] `group.id`, `client.id`, listener `id`, and `group.instance.id` are clearly distinguished.
- [ ] Partition assignments, committed offsets, and consumer lag are monitored.

In Spring Kafka, `group.id` defines the subscription identity that consumers join. Sharing a group ID lets replicas split work; using different group IDs gives workflows independent reading progress on the same topic. Stable naming and clear conventions make deploying, scaling, and operating consumers much more predictable.

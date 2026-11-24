# Monitoring Consumer Groups

A consumer group is the unit Kafka uses to distribute partition reading across multiple consumers processing the same data stream. Monitoring consumer groups lets operations teams see whether a group is active, how many members exist, which member owns which partition, whether rebalances happen continuously, and whether offsets are committed on schedule.

In Spring Kafka, a consumer group is configured via `group.id` or the `groupId` attribute on `@KafkaListener`. When running multiple application instances with the same group ID, Kafka distributes partitions across instances to scale processing capacity. Therefore, operating a group requires observing broker state, consumer members, listener containers, and offsets together.

## 1. What problem does a consumer group solve?

A topic can have multiple partitions. A consumer group enables multiple consumers to coordinate reading that topic:

```text
Topic: orders
  partition 0
  partition 1
  partition 2
  partition 3

Consumer group: orders-service
  consumer A -> partition 0, 1
  consumer B -> partition 2
  consumer C -> partition 3
```

Within the same group, each partition is assigned to at most one consumer member at a time. This lets members share the workload without actively reading duplicate copies of the same partition.

A single topic can be read independently by multiple groups:

- `orders-service` reads to update order state.
- `orders-analytics` reads to aggregate analytics data.
- `orders-audit` reads to store audit trails.

Each group maintains its own committed offsets. If applications need to independently receive every event, use distinct group IDs. If multiple instances need to share load, they use the same group ID.

Do not share the same group ID between two workloads with different processing purposes just because they read the same topic; otherwise Kafka distributes partitions between the two workloads and neither workload receives all records.

## 2. Group ID, client ID, and member ID

These three identifiers serve different roles:

| Identifier | Role |
|---|---|
| `group.id` | Identifies the consumer group and the namespace storing committed offsets |
| `client.id` | Identifies a Kafka client in logs, metrics, and quotas |
| `member.id` | Identifies a consumer member within the group; usually assigned by Kafka during join |

A group can have multiple members. Each member has its own client ID to make logs and metrics easier to trace. Set meaningful client IDs containing service, instance, and listener details to pinpoint which consumer caused an issue.

Example:

```properties
group.id=orders-service
client.id=orders-service-instance-2
```

Spring Kafka can configure the group ID at the consumer factory level:

```yaml
spring:
  kafka:
    consumer:
      group-id: orders-service
      client-id: orders-service
```

Or declare it per listener:

```java
@KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "orders-service"
)
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
```

If multiple listeners share a consumer factory, verify explicitly which listener uses which group ID. Never infer the group ID solely from a bean name or container name.

## 3. Consumer group lifecycle and states

The Kafka coordinator manages group membership and partition assignments. When a consumer starts, it joins the group, receives an assignment, sends heartbeats, and continues polling data. When membership or metadata changes, the group can rebalance.

Common group states:

| State | Operational meaning |
|---|---|
| `Empty` | The group has no active members; committed offsets may still be retained |
| `PreparingRebalance` | The coordinator is preparing to redistribute partitions |
| `CompletingRebalance` | Finalizing the assignment and waiting for all members to rejoin |
| `Stable` | The group has a stable assignment |
| `Dead` | The group has been removed from the coordinator |
| `Unknown` | The tool could not determine the state |

State names or the set of states may vary by Kafka version and group protocol. Newer consumer protocols may display additional states. In operations, cross-check against the output of the exact Kafka version in use.

A group in `Empty` state is not automatically an error: the service might be intentionally stopped. However, if a continuously running group stays `Empty` for long, check whether the application started its listeners, broker connectivity, group ID configuration, and consumer startup errors.

## 4. Observing groups with kafka-consumer-groups.sh

List existing groups:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --list
```

Inspect partitions and committed offsets of a group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --describe \
  --group orders-service
```

If the cluster enables SASL/TLS, pass a client config authorized to read the group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server broker-1.example.net:9093 \
  --command-config admin-client.properties \
  --describe \
  --group orders-service
```

Inspect members and partition assignments:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --describe \
  --group orders-service \
  --members \
  --verbose
```

Inspect group state:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --describe \
  --group orders-service \
  --state
```

When reading the output, focus on:

- Whether the group has the right name and topic subscriptions.
- Whether the current member count matches the expected number of instances.
- Which member is assigned to each partition.
- Whether any partition is unassigned or a member has an unusual assignment.
- Whether the group is `Stable` or repeatedly entering rebalances.
- Whether committed offsets are advancing or stuck for a long period.

Consumer lag is another perspective on the group and is covered separately in the consumer lag lesson. When checking a group, treat lag as a complementary signal rather than the entire state of the group.

## 5. Inspecting groups with Kafka AdminClient

You can use `AdminClient` to build internal admin pages or monitoring jobs. AdminClient lets you list groups, describe groups, read members, and inspect committed offsets.

Example reading state and assignments:

```java
import java.util.Set;
import java.util.Properties;
import java.util.Map;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.ConsumerGroupDescription;
import org.apache.kafka.clients.admin.MemberDescription;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;

class ConsumerGroupInspector {

    void inspect(String bootstrapServers, String groupId)
            throws Exception {

        Properties properties = new Properties();
        properties.put("bootstrap.servers", bootstrapServers);

        try (AdminClient admin = AdminClient.create(properties)) {
            ConsumerGroupDescription description =
                    admin.describeConsumerGroups(Set.of(groupId))
                            .describedGroups()
                            .get(groupId)
                            .get();

            System.out.println("groupId = " + description.groupId());
            System.out.println("state = " + description.state());
            System.out.println("coordinator = " + description.coordinator());

            for (MemberDescription member : description.members()) {
                System.out.println("memberId = " + member.consumerId());
                System.out.println("clientId = " + member.clientId());
                System.out.println("host = " + member.host());
                System.out.println(
                        "partitions = "
                                + member.assignment().topicPartitions()
                );
            }
        }
    }
}
```

This snippet is a minimal synchronous example. In production, set timeouts on KafkaFutures, handle non-existent groups, broker unavailability, and authorization errors. Avoid invoking AdminClient on every UI request; use a service with a clear lifecycle and cache results briefly if appropriate.

Reading committed offsets of a group:

```java
// Place inside the try (AdminClient admin = ...) block of the example above.
Map<TopicPartition, OffsetAndMetadata> offsets =
        admin.listConsumerGroupOffsets(groupId)
                .partitionsToOffsetAndMetadata()
                .get();
```

Assignment info answers which member currently owns each partition. Committed offsets answer how far the group has persisted its read progress. Both complement each other rather than replacing one another.

## 6. Monitoring consumer groups in Spring Kafka

Spring Kafka manages listener containers via `KafkaListenerEndpointRegistry`. Assign a stable ID to each listener so containers can be inspected and controlled by ID.

```java
@KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "orders-service"
)
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
```

You can retrieve the container from the registry:

```java
import java.util.Collection;

import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
class ListenerContainerInspector {

    private final KafkaListenerEndpointRegistry registry;

    ListenerContainerInspector(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    void inspectOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");

        if (container == null) {
            return;
        }

        boolean running = container.isRunning();
        Collection<TopicPartition> assigned =
                container.getAssignedPartitions();

        System.out.println("running = " + running);
        System.out.println("assigned = " + assigned);
    }
}
```

`isRunning()` indicates whether the container lifecycle is running or stopped. `getAssignedPartitions()` lets you observe the partition assignment reported by the container; it may be null before the container receives an assignment. With `ConcurrentMessageListenerContainer`, the parent container manages multiple child containers, so check your API/version when inspecting per-child details.

A running container status does not prove the broker has assigned partitions or that the listener is processing successfully. Cross-check the registry, AdminClient, metrics, and consumer logs.

## 7. One listener container and multiple consumer members

In Spring Kafka, the `concurrency` property on a listener container can create multiple consumer threads for the same listener. Each child container uses its own Kafka consumer and joins the group under the configured group ID.

Example:

```yaml
spring:
  kafka:
    listener:
      concurrency: 3
```

Or configured directly on the listener:

```java
@KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "orders-service",
        concurrency = "3"
)
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
```

If you deploy 2 application instances, each with concurrency 3, the group can have up to 6 consumer members from that listener. Actual member count also depends on configuration, container lifecycle, subscriptions, and partition count.

If a topic has 4 partitions while the group has 6 members, at most 4 members can own partitions; the remaining members sit idle. Increasing concurrency does not create extra partitions or scale parallelism beyond the partition limit.

## 8. Partition assignment and assignors

Kafka uses a partition assignor to decide which partitions are assigned to which members. Common strategies:

| Assignor | General characteristics |
|---|---|
| `RangeAssignor` | Assigns contiguous partition ranges per topic; can produce uneven distribution across multiple topics |
| `RoundRobinAssignor` | Distributes partitions in round-robin order across members; generally balances total partition counts better |
| `StickyAssignor` | Tries to preserve previous assignments where possible, minimizing partition movement |
| `CooperativeStickyAssignor` | Combines stickiness with incremental cooperative rebalancing to avoid revoking all assignments at once |

The right strategy depends on the number of topics, partitions, members, and client compatibility. Do not arbitrarily mix assignors across instances in the same group. During rolling upgrades, follow the compatibility procedure for your Kafka version and chosen assignor.

You can configure the assignor in consumer properties:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[partition.assignment.strategy]": org.apache.kafka.clients.consumer.CooperativeStickyAssignor
```

Use this assignor only when all members in the group and the Kafka client version support the cooperative protocol. When migrating from an eager assignor, follow your Kafka version's migration sequence to avoid incompatible members.

## 9. Events that trigger a group rebalance

Rebalancing is a normal mechanism for a group to redistribute partitions when membership or subscriptions change. However, overly frequent rebalances reduce useful processing time.

Common causes include:

- A new instance joins the group or an instance shuts down.
- A consumer crashes or loses connectivity.
- A listener takes too long to process and the consumer misses calling `poll()` within the limit.
- Heartbeats fail to reach the broker in time.
- Partitions are added to a topic or subscriptions change.
- The consumer group changes its assignor or membership configuration.
- Rolling deployments restart multiple instances nearly simultaneously.

During a rebalance, consumers may pause processing while assignments shift. Monitor rebalance frequency, how long the group remains unstable, member count, and assigned partition counts.

Not every rebalance is an incident. Evaluate frequency, duration, and SLA impact before changing configuration.

## 10. Heartbeat, session timeout, and poll interval

Three settings heavily affect membership:

| Property | Role |
|---|---|
| `heartbeat.interval.ms` | How often the consumer sends heartbeats while part of the group |
| `session.timeout.ms` | How long the coordinator waits for a heartbeat before treating a member as disconnected |
| `max.poll.interval.ms` | Maximum time between two `poll()` calls before the consumer is considered no longer progressing |

`heartbeat.interval.ms` is normally set significantly smaller than `session.timeout.ms`. `max.poll.interval.ms` must be large enough for normal batch processing duration, though raising it too high delays detection of hung consumers.

Example client configuration:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[heartbeat.interval.ms]": 3000
        "[session.timeout.ms]": 10000
        "[max.poll.interval.ms]": 300000
        "[max.poll.records]": 100
```

These are illustrative values only. Measure record/batch processing times and downstream latency before selecting thresholds. If a listener runs unbounded slow tasks, increasing `max.poll.interval.ms` will not fix the root cause; redesign the processing or manage pause/resume and commits appropriately.

## 11. Static membership with group.instance.id

Static membership uses `group.instance.id` to stably identify a consumer instance. When a member temporarily disconnects and returns within the allowed window, Kafka can keep its assignment and reduce unnecessary rebalances.

Example:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[group.instance.id]": orders-service-pod-0
```

Every concurrent consumer member in the same group must have a unique `group.instance.id`. If two members use the same ID, the broker can fence one member with a duplicate instance ID error. For listeners with concurrency greater than 1, verify whether your Spring Kafka version automatically appends a suffix per child consumer; if not, assign distinct IDs to each child. Never assume a single pod-level value is always unique enough.

In Kubernetes, you can combine a StatefulSet ordinal with the child index or another stable identity to build the ID. Do not reuse the same fixed value across all replicas. Static membership also does not eliminate rebalances in every scenario; it changes how the broker handles members leaving and rejoining.

## 12. Scaling a consumer group

Consumer group parallelism is bounded by the number of partitions assignable to the group. To increase throughput, evaluate all of the following together:

- Topic partition count.
- Number of active consumer members.
- Listener container concurrency per instance.
- Per-record throughput and latency.
- Capacity of databases or downstream services.
- Key distribution and partition skew.
- Rebalance frequency and batch processing time.

For example, if a topic has 8 partitions and a group has 4 members, each member can receive roughly 2 partitions under a balanced assignor. Scaling to 10 members adds no further parallel reading; 2 members will receive no partitions.

Increasing partition count can raise parallelism, but it also alters key-to-partition mapping for new records. If business logic depends on per-key ordering, assess the impact before expanding partition count.

## 13. Rolling deployments and graceful shutdown

When deploying a new version, old consumer members leave the group and new members join. Stopping many instances simultaneously can cause repeated rebalances and backlog spikes.

A stable deployment sequence:

1. Verify the group is healthy and check the current member count.
2. Deploy instances one by one or in small batches.
3. Let listener containers stop gracefully so consumers leave the group cleanly in lifecycle order.
4. Wait for the new instance to start, join the group, and receive partitions.
5. Check group state, member count, and assignments after each batch.
6. Monitor listener errors, commits, rebalances, and downstream services.
7. Proceed to the next batch once the group stabilizes.

Spring Kafka listener containers support lifecycle start/stop. You can set `shutdownTimeout` on `ContainerProperties` to bound wait time when stopping a container; choose an appropriate value based on processing duration and commit semantics.

Avoid `kill -9` or terminating all instances of a group at once unless necessary. If records are in flight, verify the container has time to finish or that safe retry/reprocessing is in place.

## 14. Resetting offsets is a risky operational action

Resetting offsets changes where a group will resume reading. This operation can skip records or replay already-processed records; only perform it when the goal, topic/partition scope, and proper operational approval are established.

Example previewing a reset to earliest:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --group orders-service \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --dry-run
```

After reviewing the dry-run output, confirm the group has no active consumers and understand the impact before running with `--execute`:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --group orders-service \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --execute
```

Other reset options may include `--to-latest`, `--shift-by`, `--to-offset`, or `--to-datetime` depending on Kafka version. Read CLI `--help` and always run `--dry-run` first. Some versions require the group to have no active members before permitting a reset.

Before executing, you should:

- Record the current committed offsets.
- Clearly identify the affected topics and partitions.
- Assess potential duplicate side effects on replay.
- Confirm retention still holds the records to be re-read.
- Have a rollback plan or saved offsets to restore.
- Monitor consumers after the reset and verify business data.

Never reset offsets just to make lag drop or to clear a dashboard alert.

## 15. ACLs and permissions to inspect consumer groups

A client can authenticate successfully yet lack permission to describe groups or read committed offsets. When using SASL/ACLs, admin tools and AdminClient must use a principal granted the proper permissions.

Commonly involved permissions:

- `Describe` permission on the group to view group metadata.
- `Read` permission on the group for operations involving committed offsets/consumer groups depending on the Kafka version's authorization semantics.
- `Describe` permission on the topic to read metadata.
- Appropriate cluster permissions for specific administrative operations.

Do not grant `ClusterAction` or superuser privileges to dashboards just to view groups. Grant only the necessary ACLs and verify with the monitoring tool's actual principal, rather than using a shared administrator account for business apps.

## 16. Diagnosing common scenarios

| Symptom | Possible causes | Investigation path |
|---|---|---|
| Group in `Empty` | No active consumers, listener not started, or all instances stopped | Check registry, deployments, broker connectivity, and group ID |
| Group stuck in `PreparingRebalance` | Members not completing join/sync or continuous rebalances | Check coordinator logs, network, heartbeats, and members |
| Fewer members than instances | Listener not running, mismatched group IDs, or startup error | Check `@KafkaListener`, factories, and application logs |
| Many idle members | More members than partitions or empty subscription | Compare partition count against assignments |
| One member owns more partitions | Assignor behavior, multi-topic subscription, or uneven partition counts | Check assignments and assignor |
| Repeated rebalances | Poll interval, heartbeats, restarts, or unstable network | Check listener timing, timeouts, and deployments |
| Member fenced | Duplicate `group.instance.id` or old member has not left group | Check identity configuration per replica |
| Group stable but records not processed | Listener paused, swallowed exceptions, or blocked downstream | Check container state, listener logs, and processing metrics |
| Cannot inspect group with AdminClient | Missing ACL permissions or broker unavailable | Check security config and authorization |
| Duplicates after offset reset | Consumers re-read already-processed records | Check idempotency keys and side effects |

## 17. Consumer group monitoring runbook

When a consumer group alert fires, follow this sequence:

1. Identify the exact group ID, topic, and environment.
2. Check group state using `kafka-consumer-groups.sh --describe --state`.
3. Check member count and partition assignments using `--members --verbose`.
4. Compare expected member count with running instances and Spring Kafka concurrency.
5. Inspect application logs around member join/leave, rebalances, and listener exceptions.
6. Check heartbeats, `max.poll.interval.ms`, batch processing duration, and networking.
7. Check committed offsets and consumer lag to measure group progress.
8. Check downstream services, databases, and thread pools if consumers are fetching but processing slowly.
9. If offsets must be altered, save current offsets, run dry-run, and evaluate replay before executing.
10. After remediation, confirm the group returns to `Stable`, assignments are complete, and commits continue advancing.

Record timestamps, group ID, member ID, client ID, topic-partitions, group state, and actions taken in the incident record. Avoid writing credentials or sensitive payloads into operational logs.

## 18. Consumer group operations checklist

1. Assign distinct group IDs to independent workloads; share a group ID across replicas sharing load.
2. Configure client IDs that identify both service and instance.
3. Monitor group state, member count, and partition assignments.
4. Check concurrency relative to partition count.
5. Track rebalance rate and reasons members leave the group.
6. Tune `heartbeat.interval.ms`, `session.timeout.ms`, and `max.poll.interval.ms` based on real workload measurements.
7. Use unique `group.instance.id` values when applying static membership.
8. Use rolling deployments and graceful shutdown to minimize unnecessary rebalances.
9. Use AdminClient/CLI with least-privilege ACLs to inspect groups.
10. Record committed offsets before performing any reset.
11. Run `--dry-run` before any reset and confirm the group is inactive.
12. Monitor lag, commits, listener latency, and downstream health alongside group state.

Monitoring consumer groups means observing membership and how Kafka distributes partitions across consumers, whereas consumer lag measures reading progress against the log. Combining both views with listener container lifecycle, rebalances, commits, and downstream health helps operations pinpoint root causes whenever a Spring Kafka flow stops processing reliably.

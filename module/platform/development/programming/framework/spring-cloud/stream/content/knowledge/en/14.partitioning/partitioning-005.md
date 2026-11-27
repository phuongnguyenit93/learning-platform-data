# Configuring the Consumer Side with partitioned, instanceCount, and instanceIndex

Message partitioning only works effectively when the consumer side is configured to match how the producer partitions data. In Spring Cloud Stream, a consumer binding has the `partitioned` property; the application can also declare `instanceCount` and `instanceIndex` to describe the total number of instances participating in processing and the current instance's position in the binder's partitioning model.

These three properties are not three ways of writing the same thing. `partitioned` enables partition-aware mode for the binding. `instanceCount` indicates how many application instances participate in the processing group. `instanceIndex` identifies the index of a specific instance. Instances must be configured consistently so messages are routed to the right processing group without unexpected omissions or duplicate handling.

This lesson belongs to the **Partitioning** chapter of the `SPRING_CLOUD_STREAM` module, focusing on consumer-side configuration in the `Supplier`/`Function`/`Consumer` function model and binders for Kafka, RabbitMQ, or Pulsar. We will examine how to configure bindings, assign indices to replicas, scale instance counts, handle restarts, and distinguish the generic partitioning model from each broker's native partitioning mechanism.

## 1. Why Does the Consumer Need to Know About Partitions?

Partitioning splits a data stream into multiple parts to increase parallel processing capacity. The producer typically selects a partition based on a business key such as `orderId`, `customerId`, or `accountId`. Messages with the same key can be placed into the same partition to preserve ordering within that key's scope.

On the consumer side, multiple instances collaborate to process a destination and a consumer group. If the binder uses Spring Cloud Stream's partitioning model, the consumer needs to know:

- Whether the binding participates in a partitioned stream.
- The total number of participating instances.
- Which index the current instance holds.

For example, with six partitions and three instances:

```text
Destination: orders.events

Partition 0 ----+
Partition 1 ----+----> Instance 0

Partition 2 ----+
Partition 3 ----+----> Instance 1

Partition 4 ----+
Partition 5 ----+----> Instance 2
```

The diagram only illustrates splitting work across instances. How the broker or binder actually assigns partitions depends on the binder, subscription type, consumer group, and producer configuration. Do not infer that every binder uses the same partition assignment algorithm.

If the producer sends messages by key but the consumer does not participate in the same partitioning model, the application may still receive messages, yet not necessarily achieve the distribution or ordering intended by the design. Therefore, producer and consumer configurations must be treated as two halves of the same contract.

## 2. The Three Consumer-Side Properties

### `partitioned`

`partitioned` is a property on a consumer binding declaring that the binding receives data under a partitioned model. In YAML, the property is placed under the binding's `consumer` section:

```yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          consumer:
            partitioned: true
```

A value of `true` tells the binder that the consumer should participate in the partition-aware handling supported by the binder. It does not automatically create extra partitions on the producer, does not replace the consumer group, and does not determine how many replicas are running.

### `instanceCount`

`instanceCount` is the total number of application instances participating in the same processing model. For example, if the application is deployed as three replicas, `instanceCount` is `3` across all three replicas.

This is the number of application instances—not the number of processing threads inside one JVM, not the topic's partition count, and not the number of messages in a batch.

### `instanceIndex`

`instanceIndex` is the index of the current instance. Indices normally start at `0` and must be unique within the declared total instance count. With three instances, valid indices are `0`, `1`, and `2`.

| Instance | `instanceCount` | `instanceIndex` |
|---|---:|---:|
| Replica A | 3 | 0 |
| Replica B | 3 | 1 |
| Replica C | 3 | 2 |

These values must be supplied individually to each replica. If all three replicas use `instanceIndex: 0`, the configuration no longer describes three distinct instances. If one instance declares `instanceCount: 2` while the remaining instances declare `3`, the binder may compute or route differently across processes.

## 3. Complete Consumer Binding Configuration

Suppose an application has a `projectOrder` function that receives order events. The input binding is `projectOrder-in-0`:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderEvent(String orderId, String customerId, String status) {}

@Configuration
class OrderProjectionConfiguration {

    @Bean
    Consumer<OrderEvent> projectOrder(OrderProjection projection) {
        return event -> projection.apply(event);
    }
}
```

Application-wide configuration:

```yaml
spring:
  cloud:
    function:
      definition: projectOrder
    stream:
      instance-count: ${INSTANCE_COUNT:3}
      instance-index: ${INSTANCE_INDEX:0}
      bindings:
        projectOrder-in-0:
          destination: orders.events
          group: order-projection
          content-type: application/json
          consumer:
            partitioned: true
```

In this configuration:

- `projectOrder` is the activated function.
- `projectOrder-in-0` is the consumer binding.
- `destination` is the message stream to which the binder connects.
- `group` identifies the consumer group coordinating processing.
- `partitioned: true` declares that the binding consumes under a partitioned model.
- `instance-count` and `instance-index` are read from environment variables so each replica can receive its own value.

`instance-count` and `instance-index` are application-level properties under `spring.cloud.stream`, not nested inside a binding's `consumer` block. In YAML, Spring Boot uses kebab-case; the Java property names are usually written as `instanceCount` and `instanceIndex`.

## 4. Assigning Indices to Each Replica

With three replicas, the environment configuration must share the same total instance count and have distinct indices:

```text
Replica A:
  INSTANCE_COUNT=3
  INSTANCE_INDEX=0

Replica B:
  INSTANCE_COUNT=3
  INSTANCE_INDEX=1

Replica C:
  INSTANCE_COUNT=3
  INSTANCE_INDEX=2
```

In Kubernetes, a `StatefulSet` can be used to obtain a stable ordinal for each pod, and that ordinal can be mapped to `INSTANCE_INDEX`. If using a `Deployment` where pod names change and there is no dedicated index-assignment mechanism, do not let all pods share the same default value. You need an orchestration or runtime configuration mechanism that guarantees unique and consistent indices.

For example, a manifest configuration can pass environment variables derived from the ordinal field or from a dedicated initialization mechanism. How the ordinal is obtained depends on the deployment platform; the critical requirement is that each process receives its own `INSTANCE_INDEX` and the same `INSTANCE_COUNT`.

Do not rely on `INSTANCE_INDEX: 0` as a production default across all replicas. A default value is handy when running a single instance locally, but if multiple replicas start without environment variables supplied, they will all declare index `0`.

## 5. Coordinating with Producer Configuration

A partitioned consumer only works properly when the producer emits messages using the matching partitioning convention. For example, a producer using `orderId` as the key:

```yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.events
          content-type: application/json
          producer:
            partition-key-expression: payload.orderId
            partition-count: 6
```

Here the producer selects the key from `payload.orderId` and declares an expected partition count of `6`. The consumer configuration must match the actual topology and how the binder handles partitions. `partition-count` on the producer is not `instance-count` on the consumer:

| Property | Side | Meaning |
|---|---|---|
| `partition-count` | Producer | Number of partitions the producer uses when calculating or configuring partitioning |
| `partitioned` | Consumer binding | Declares that the consumer participates in partitioned consumption mode |
| `instance-count` | Consumer/application | Total number of participating application instances |
| `instance-index` | Consumer/application | Index of the current instance |

The example of six partitions and three instances shows that each instance can process multiple partitions. The partition count does not need to equal the instance count. If the partition count is smaller than the instance count, some instances may not be assigned a partition or may receive no data depending on the broker mechanism. If the partition count is larger than the instance count, each instance can receive multiple partitions.

Producer and consumer must agree on the destination, group/subscription, partition count, and routing key. If the producer changes how it generates partition keys or changes the partition count, evaluate the impact on ordering and existing state.

## 6. Meaning of `instanceCount` and `instanceIndex` When Scaling

Suppose a system initially has three instances and later scales to four. In a model requiring `instanceCount` and `instanceIndex`, all instances must transition together to `instanceCount: 4` with indices `0`, `1`, `2`, and `3`.

Do not simply add a fourth replica with `instanceIndex: 3` while the three older replicas still declare `instanceCount: 3`. During the transition, instances will not share the same view of the partitioning model. Depending on the binder, this can cause inconsistent distribution or leave partitions unconsumed.

Controlled scaling procedure:

1. Check the existing partition count and the broker's serving capacity.
2. Choose a new instance count suited to throughput and resource limits.
3. Update `instanceCount` consistently across all participating instances.
4. Assign a unique `instanceIndex` in the range from `0` to `instanceCount - 1`.
5. Roll out using a strategy that avoids leaving two incompatible configurations consuming concurrently for long.
6. Verify bindings, groups, partition assignments, and backlog after scaling.

Scaling down requires similar coordination. Do not let two processes share the same index while an old process is still active. Allow a handoff window, drain in-flight messages, and confirm the old consumer has left the group before reusing an index.

## 7. Distinguishing Instances from Concurrency

`instanceCount` is the number of participating application processes/replicas. `instanceIndex` is the index of the current process. `concurrency` is typically the number of parallel consumer threads or listeners a binder creates within one process. These concepts do not replace each other.

Example:

```yaml
spring:
  cloud:
    stream:
      instance-count: 3
      instance-index: 1
      bindings:
        projectOrder-in-0:
          destination: orders.events
          group: order-projection
          consumer:
            partitioned: true
            concurrency: 2
```

The application in this example is instance `1` out of three total instances. The binding also requests `concurrency: 2`, if supported by the binder. Concurrency can create multiple consumers or listeners within the same process; it does not turn one process into two different `instanceIndex` values.

Increasing concurrency does not automatically increase the partition count. If a topic has three partitions and a total of nine consumer threads across a group, many threads will remain unassigned. Determine parallelism limits from the partition count, replica count, concurrency, and binder capabilities.

## 8. Differences by Binder

Spring Cloud Stream provides a shared configuration model, but actual partition distribution mechanisms depend on the broker:

| Binder | Typical Distribution Mechanism | Role of Consumer-Side Configuration |
|---|---|---|
| Kafka | Kafka consumer group coordinator distributes topic partitions across consumers in the same group | Group and consumer/concurrency count are central; Kafka manages assignment and rebalancing automatically. `instanceIndex` does not replace Kafka's native assignment mechanism |
| RabbitMQ | Binder may implement partitioned queues/routing per topology and instance properties | `partitioned`, `instanceCount`, and `instanceIndex` can participate in determining which queues or data slices belong to an instance per binder configuration |
| Pulsar | Consumers receive messages via subscriptions; load sharing depends on subscription type and key/partition | Subscription type, topic partitions, and key-shared behavior dictate distribution; do not assume `instanceIndex` replaces Pulsar's assignment |

With Kafka, multiple instances sharing the same consumer group have partitions distributed automatically by Kafka. When the instance count changes, Kafka performs a rebalance. You do not manually assign partitions via `instanceIndex` as though Kafka lacked a group coordinator. Check the documentation for your Kafka binder version to see which generic properties apply.

With RabbitMQ, partitioning can be implemented using separate queues and routing keys. When enabling a partitioned consumer, the binder needs to know the instance count and index to map the right slice of data to each instance. Inspect the queue names, exchanges, bindings, and topology created by the binder.

With Pulsar, the subscription type is a critical decision. `Exclusive`, `Failover`, `Shared`, and `Key_Shared` coordinate consumers differently. If per-key ordering is required, choose an appropriate subscription type and ordering key. `instanceCount`/`instanceIndex` does not automatically turn a subscription into `Key_Shared`.

Therefore, the generic configuration above illustrates Spring Cloud Stream's partition-aware model; do not copy it verbatim across every binder without checking binder semantics and dependency versions.

## 9. Consumer Groups and Partitions Are Distinct Concepts

A consumer group defines a set of consumers collaborating to share load on a stream. Partitions divide the stream into parts that can be processed in parallel. In Kafka, the group coordinator assigns partitions to consumers within the same group. Another group can read the same topic independently with its own offsets.

In other binders, the group concept may map to queues or subscriptions. Partitioning may be implemented via routing keys, queue topologies, or subscription types. Therefore, distinguish:

- `group`: name of the consumer group and scope of coordination.
- `partitioned`: whether the binding participates in the partitioned consumption model.
- `instanceCount`: number of application instances in that model.
- `instanceIndex`: position of the specific instance.
- `concurrency`: consumer parallelism within a single instance, if supported by the binder.

If replicas use different groups, they may receive independent copies of the stream instead of sharing load. Configuring `instanceIndex` will not fix a mismatched `group` across replicas.

## 10. What Happens When an Instance Restarts or Loses Connection?

An instance may restart due to upgrades, process crashes, or node failures. When that happens, the broker/binder applies its own recovery mechanism:

- Kafka: the consumer leaves the group or its heartbeat expires, and partitions are rebalanced to remaining consumers. Offsets and commit behavior determine which messages are re-read.
- RabbitMQ: the consumer channel closes, and unacknowledged messages may be requeued depending on configuration; queue and partition topology must still be correct.
- Pulsar: the consumer disconnects, and the subscription cursor and subscription type determine how messages are redelivered to active consumers.

`instanceIndex` does not persist message processing state, nor does it replace offsets, acknowledgments, or subscription cursors. It describes the identity/position of an instance within a partition-aware configuration. Ensuring messages are neither lost nor applied twice still requires delivery guarantees and idempotent consumers.

When restarting an instance, ensure the index is reassigned properly and that two processes never operate with the same index if the binder model requires unique indices. If the application uses a `StatefulSet`, stable ordinals can help reuse an index safely after the old instance has completely stopped.

## 11. Common Misconfigurations

| Configuration or Situation | Possible Consequence | Remedy |
|---|---|---|
| All replicas have `instance-index: 0` | Multiple instances declare the same position | Supply a unique index to each replica |
| `instance-count` differs across replicas | Processes calculate against inconsistent models | Use the same total instance count across the entire group |
| Index is negative or greater than/equal to count | Index is outside the valid range | Verify `0 <= instanceIndex < instanceCount` |
| `partitioned` is omitted | Binder does not enable desired partition-aware consumer mode | Set `consumer.partitioned: true` if required and supported by the binder |
| Different `group` across replicas | Instances no longer coordinate in the same group | Unify destination and group |
| Producer and consumer have mismatched partition topology | Messages may distribute unexpectedly | Align partition count, key, and binder configuration |
| Increasing replicas without updating count/index | Some partitions may go unassigned or routing model becomes inconsistent | Scale through a controlled process |
| Confusing `concurrency` with `instanceCount` | Configuring consumer thread count instead of replica count | Manage the two properties separately |
| Using `instanceIndex` to manually assign Kafka partitions | Conflicts with Kafka's group assignment mechanism | Let the Kafka coordinator manage assignments; check specific binder requirements |

## 12. Startup Configuration Validation

You can validate environment values before initializing consumers to catch misconfigurations early. Example of a simple validator:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import jakarta.annotation.PostConstruct;

@Component
class PartitionInstanceConfigurationCheck {

    private final int instanceCount;
    private final int instanceIndex;

    PartitionInstanceConfigurationCheck(
            @Value("${spring.cloud.stream.instance-count:1}") int instanceCount,
            @Value("${spring.cloud.stream.instance-index:0}") int instanceIndex) {
        this.instanceCount = instanceCount;
        this.instanceIndex = instanceIndex;
    }

    @PostConstruct
    void validate() {
        if (instanceCount < 1) {
            throw new IllegalStateException("instanceCount must be positive");
        }
        if (instanceIndex < 0 || instanceIndex >= instanceCount) {
            throw new IllegalStateException("instanceIndex is outside the configured range");
        }
    }
}
```

This validator only checks the arithmetic range of the two properties. It cannot verify whether other replicas are using unique indices or the same `instanceCount`. That must be guaranteed by the deployment platform, service discovery, or centralized orchestration.

In production, put `instanceCount` and `instanceIndex` in centrally managed configuration or derive them from platform metadata. Log these values at startup for easier troubleshooting, without logging sensitive information.

## 13. Testing Partition-Aware Consumers

Testing should verify both per-instance configuration and message distribution outcomes:

| Scenario | How to Simulate | What to Verify |
|---|---|---|
| Single instance | `instanceCount=1`, `instanceIndex=0` | Consumer starts and receives messages as configured |
| Three valid instances | Count `3`, indices `0`, `1`, `2` | Each instance receives the appropriate data slice per the binder |
| Duplicate index | Two instances both using index `1` | Misconfiguration is detected or conflicting behavior is observed |
| Out-of-range index | Count `3`, index `3` | Validator rejects the configuration |
| Inconsistent count | Two instances use count `2`, one uses count `3` | Deployment validation catches the mismatch |
| Scaling instances up | Transition from three to four | Partition assignment and backlog stabilize after scaling |
| Instance restart | Stop one consumer and restart it | Messages recover per broker semantics and the index is reassigned cleanly |
| Producer changes partition key | Change key expression or partition count | Verify ordering and distribution of new messages |
| Broker-specific assignment | Run against real Kafka/RabbitMQ/Pulsar | Confirm the binder executes the real partitioning mechanism properly |

Unit tests for a validator do not replace integration tests. With Kafka, observe consumer groups and partition assignments. With RabbitMQ, inspect actual queues, exchanges, routing keys, and consumers. With Pulsar, inspect topics, subscription types, and consumer assignments. The Test Binder only verifies Spring's abstraction and does not fully prove real broker topology or algorithms.

## 14. Observability and Operations

Metrics worth monitoring:

- `instanceCount` and `instanceIndex` of each replica at startup.
- Actual running replica count versus configured instance count.
- Partition assignment or queue/subscription assignment per binder.
- Consumer lag, backlog, and oldest message age.
- Throughput, processing duration, retries, and redelivery counts.
- Rebalance count, consumer disconnects, and recovery time.
- Load distribution across instances to spot overloaded or idle instances.

If an instance receives no messages, inspect `group`, `index`, `count`, partition assignments, and backlog before concluding that the producer is not sending. If one instance receives far too many messages, check whether the partition key distributes evenly; an overly hot key can force one partition and instance to carry most of the load.

Logs should include application instance ID, `instanceIndex`, destination, group, and partition/queue/subscription identifier if provided by the binder. Avoid turning arbitrary message IDs or tenant IDs into high-cardinality metric labels.

## 15. Recommended Rollout Workflow

When configuring a partitioned consumer:

1. Identify the destination, consumer group, and actual partition count.
2. Choose a producer partition key so messages requiring ordering share the same key.
3. Identify the binder in use and how it performs partition assignment.
4. Enable `consumer.partitioned` when required by the binder model.
5. Set `instanceCount` to the total number of replicas participating in the same model.
6. Provide a unique, valid `instanceIndex` to each replica.
7. Keep destination, group, and count consistent across replicas.
8. Distinguish replica count from `concurrency` inside each process.
9. Test scaling up/down, restarts, rebalances, and broker failures.
10. Monitor assignments, lag, backlog, and load distribution after rollout.

## 16. Self-Check

- [ ] Can explain the role of `consumer.partitioned`.
- [ ] Can distinguish `instanceCount` from partition count and consumer thread count.
- [ ] Can explain `instanceIndex` and its valid value range.
- [ ] Can configure `spring.cloud.stream.instance-count` and `instance-index` via environment variables.
- [ ] Can ensure all replicas use the same `instanceCount` and unique indices.
- [ ] Can distinguish a consumer group from a partition.
- [ ] Can explain why producer partition keys and consumer topology must be compatible.
- [ ] Can distinguish native Kafka/Pulsar assignment mechanisms from the binder's partition-aware model.
- [ ] Can design workflows for scaling, restarting, and testing misconfigurations.
- [ ] Know how to monitor partition assignments, lag, and load distribution in operations.

## Conclusion

The consumer side must be configured according to the partitioning model supported by the binder. `consumer.partitioned` declares that the binding participates in partitioned processing; `instanceCount` describes the total number of instances, and `instanceIndex` identifies the position of the current instance. Replicas must share the same count and have unique indices while aligning with the destination, group, and producer key-selection strategy. Do not confuse instance count with partition count or concurrency. Kafka and Pulsar have native broker assignment mechanisms; RabbitMQ and other binders may use their own topologies. Therefore, always test on the target binder and manage scaling and restarts cleanly to avoid misrouting, missed messages, or overlapping processing.

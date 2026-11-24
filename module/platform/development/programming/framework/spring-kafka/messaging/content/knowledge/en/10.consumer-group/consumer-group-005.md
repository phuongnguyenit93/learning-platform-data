# Consumer Group Rebalancing

A Kafka consumer group can experience changes in its members or in the number of partitions to distribute throughout its lifetime. When that happens, Kafka must recalculate which consumer is responsible for reading each partition. The process of revoking old assignments and distributing new assignments is called **rebalance**.

Rebalancing enables the group to continue operating when consumers join, leave, or fail, while also redistributing load when topics change. However, during a rebalance, reading on affected partitions may pause; listeners may observe increased latency, interrupted processing, and uncommitted records being read again. Understanding triggers, assignment strategies, and how to observe rebalances helps operate Spring Kafka more reliably.

## 1. How Does a Consumer Group Distribute Partitions?

A consumer group consists of consumers subscribing to one or more topics under the same group ID. Kafka distributes the topics' partitions among the consumers in the group. Within a group, at any given time, a partition is assigned to at most one consumer.

For example, the `orders.events` topic has six partitions and the `order-projection` group has three consumers:

```text
Topic orders.events
  P0   P1   P2   P3   P4   P5
   \   |    /    \    |    /
    \  |   /      \   |   /
   Consumer A    Consumer B    Consumer C
```

A valid assignment could be:

| Consumer | Assigned partitions |
|---|---|
| Consumer A | P0, P1 |
| Consumer B | P2, P3 |
| Consumer C | P4, P5 |

This is only an example; the actual outcome depends on the partition assignor. If the group has more consumers than partitions, some consumers will not be assigned any partitions. If a consumer leaves the group, its partitions must be redistributed to the remaining members.

## 2. What Steps Does a Rebalance Follow?

The Kafka group coordinator manages membership and orchestrates the rebalance process. In the classic group protocol, consumers exchange subscription metadata, the coordinator determines that the group needs a rebalance, one member is elected as group leader to compute the assignment via the assignor, and then the assignment is sent to the consumers.

Conceptually, the process consists of:

1. **Change detection:** the coordinator detects a new member, a departing member, an expired heartbeat, or changed subscription/partition metadata.
2. **Starting the rebalance:** the group enters a new generation. Affected consumers invoke partition revocation callbacks according to the assignment strategy.
3. **Computing the assignment:** the partition assignor determines which partition belongs to which consumer.
4. **Distributing the assignment:** consumers receive their new partitions and resume fetching, polling, and processing records.

A generation is the membership version of the group. It helps Kafka identify which generation a commit or activity request originates from. Once the group has moved to a new generation, a commit based on an old membership may be rejected because the consumer no longer belongs to the current generation.

In newer Kafka versions that include the new consumer group protocol, certain coordination details and leader/assignor roles change. Regardless of the protocol used, the operational implication remains that the group must update membership and assignments whenever member state or resources change.

## 3. Common Causes of Rebalancing

Rebalancing does not happen only during application deployments. Common triggers include:

| Cause | What happens |
|---|---|
| A new consumer joins the group | The group must redistribute partitions to account for the new member |
| A consumer stops gracefully | The consumer leaves the group and its partitions are handed to other members |
| A consumer or host fails | The coordinator detects the member no longer has valid heartbeats and removes it from the group |
| Failing to call `poll()` within the allowed interval | The consumer may be considered no longer making progress and leave the group |
| Subscription changes | Members subscribe to/unsubscribe from topics or a pattern matches a new topic |
| Topic partition count increases | The group must update assignments to distribute the new partitions |
| Assignor configuration or protocol changes | Members may need to rebalance to agree on assignments |

An application that continuously restarts, overly sensitive liveness probes, prolonged listener processing, or flaky networking can cause the group to rebalance frequently. If rebalances repeat within a short span, throughput drops and processing latency rises even when total record volume has not changed.

## 4. Heartbeat, Session Timeout, and Max Poll Interval

Three settings are commonly inspected when diagnosing consumers being removed from a group:

| Property | Role |
|---|---|
| `heartbeat.interval.ms` | Interval at which the consumer sends heartbeats to the group coordinator |
| `session.timeout.ms` | Duration the coordinator waits for a valid heartbeat before considering the consumer disconnected |
| `max.poll.interval.ms` | Maximum time between `poll()` calls; protects the group from a consumer making no processing progress |

Heartbeats tell the coordinator that the consumer is still participating in the group. `session.timeout.ms` determines how long the coordinator waits when heartbeats are missed. `max.poll.interval.ms` monitors the application's poll-calling progress. A consumer may still be sending background heartbeats while taking too long to process records and failing to poll on time; in that case, the consumer can still leave the group due to violating the max poll interval.

With synchronous listeners, batch processing time must stay within `max.poll.interval.ms` with headroom. If batches are too large or the listener calls an external service without a timeout, the consumer can exceed the limit and trigger a rebalance. Measure actual processing duration, especially high percentiles, rather than relying only on average times.

Example configuration in Spring Boot:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-projection
      properties:
        "[heartbeat.interval.ms]": 3000
        "[session.timeout.ms]": 10000
        "[max.poll.interval.ms]": 300000
```

These numbers are illustrative only. With the classic protocol, `heartbeat.interval.ms` generally needs to be significantly smaller than `session.timeout.ms`; valid bounds also depend on broker configuration. Tune according to your environment and Kafka version rather than copying blindly into production.

## 5. Eager and Cooperative Rebalancing

The partition assignor determines how partitions are distributed. How assignments are revoked strongly affects the level of disruption during a rebalance.

### Eager Rebalancing

With eager rebalancing, consumers in the group revoke all currently held partitions before receiving a new assignment. During the transition phase, the group may pause processing across all partitions belonging to the group, including partitions that theoretically do not need to move to another consumer.

The advantage is a simple process compatible with traditional eager assignors. The drawback is that the pause scope can be large, especially when the group has many consumers and partitions.

### Cooperative Rebalancing

Cooperative rebalancing allows partitions to be transferred incrementally. Consumers only revoke partitions that actually need to move; unaffected partitions can continue to be processed. If an assignment requires multiple steps, the coordinator may request an additional rebalance round to finish the handoff.

`CooperativeStickyAssignor` strives to keep assignments stable across rebalances while distributing load relatively evenly. This approach typically reduces the disruption scope when group membership changes.

To use the cooperative assignor with a supporting Kafka client, you can configure:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[partition.assignment.strategy]": org.apache.kafka.clients.consumer.CooperativeStickyAssignor
```

When deploying via rolling upgrades, follow the compatibility guidelines for your Kafka version and assignor. All consumers in the same group must have compatible strategies; do not switch assignors abruptly without accounting for older-version consumers still running.

Cooperative rebalancing reduces the number of partitions that must pause, but it does not eliminate rebalances. Consumers still have to handle revoking and receiving partitions, and the application must be prepared for revoke/assign callbacks to be invoked multiple times.

## 6. Static Membership Reduces Rebalances on Brief Restarts

By default, consumers are identified by a Kafka-managed member ID. When a consumer leaves the group, the member is removed and the group may rebalance immediately. When an application restarts briefly during a deployment, leaving and rejoining can trigger a rebalance even though the new instance effectively replaces the old one.

**Static membership** allows configuring a stable `group.instance.id` for a consumer instance. When the consumer restarts with the same ID within the session timeout window, Kafka can recognize it as the same member and reduce unnecessary rebalances.

Example property configuration for a consumer instance:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[group.instance.id]": ${KAFKA_CONSUMER_INSTANCE_ID}
```

The `KAFKA_CONSUMER_INSTANCE_ID` value must remain stable across restarts of the same instance and unique within the group at any given time. If two consumers concurrently use the same static member ID, Kafka can reject or fence one member. For a listener container with `concurrency` greater than one, ensure each actual consumer has a distinct ID in a way supported by Spring Kafka configuration.

Static membership is helpful for brief rolling restarts, but with a trade-off: when an instance is genuinely lost, the coordinator may wait for the session timeout before evicting the static member and redistributing partitions. Choosing a timeout that is too long can leave partitions held for a long time when an instance truly dies.

## 7. Observing Rebalances in Spring Kafka

Spring Kafka allows registering a `ConsumerRebalanceListener` via `ContainerProperties`. Callbacks are typically used to log assignments, release state tied to partitions about to be revoked, or initialize state for newly assigned partitions.

Example configuring a custom container factory:

```java
import java.util.Collection;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.common.TopicPartition;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ConsumerAwareRebalanceListener;

@Configuration
class RebalanceListenerConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(RebalanceListenerConfiguration.class);

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
            rebalanceAwareKafkaListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory) {

        var factory = new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties().setConsumerRebalanceListener(
                new ConsumerAwareRebalanceListener() {
                    @Override
                    public void onPartitionsRevokedBeforeCommit(
                            Consumer<?, ?> consumer,
                            Collection<TopicPartition> partitions) {
                        log.info("Partitions revoked: {}", partitions);
                        // Flush or release local state for these partitions.
                    }

                    @Override
                    public void onPartitionsAssigned(
                            Consumer<?, ?> consumer,
                            Collection<TopicPartition> partitions) {
                        log.info("Partitions assigned: {}", partitions);
                        // Initialize required state for newly assigned partitions.
                    }
                }
        );
        return factory;
    }
}
```

The listener can select this factory:

```java
@KafkaListener(
        topics = "orders.events",
        groupId = "order-projection",
        containerFactory = "rebalanceAwareKafkaListenerContainerFactory"
)
public void consume(String payload) {
    process(payload);
}
```

Callbacks execute in the context of the consumer thread. Do not perform long-blocking work inside callbacks, as that can delay rebalance completion. If the application uses per-partition local state, flush or release the right partitions in the revoke callback; on assign, restore state from a durable source before processing work that depends on that state.

Newer Kafka clients also provide an `onPartitionsLost()` callback to distinguish partitions whose ownership was lost without an opportunity for normal revocation. If you need to use this callback, check the corresponding Kafka client version and Spring Kafka API. In a partition-lost situation, do not assume the consumer can still commit offsets for those partitions.

## 8. How Rebalancing Affects Offsets and Record Processing

When a partition is revoked, the old consumer must finish its work and commit offsets according to application policy before relinquishing ownership. The Spring Kafka listener container manages commits based on the acknowledgement mode. If the listener finishes processing without committing and the partition is handed to another consumer, records may be read again starting from the latest committed offset.

Several principles help reduce errors:

- Set `enable.auto.commit=false` so Spring Kafka manages commits according to the acknowledgement mode.
- Choose an appropriate `AckMode`, such as `BATCH` for per-poll record processing or manual acknowledgement when explicit commit timing control is needed.
- Do not perform non-idempotent side effects before committing without a duplicate-processing safeguard.
- Keep work inside rebalance callbacks short and avoid calling external services with unbounded latency.
- When per-partition state is needed, persist checkpoints or durable state so a new consumer can resume safely.

Rebalancing does not lose records that have not expired past retention. The usual issue is that records may be read again because committed offsets do not yet reflect processing that just completed. Applications should be designed for at-least-once delivery and idempotency unless using a transaction mechanism spanning all operations requiring guarantees.

## 9. How to Reduce Unnecessary Rebalances

| Measure | Effect |
|---|---|
| Set timeouts for database/API calls and listener processing | Prevents exceeding `max.poll.interval.ms` |
| Choose `max.poll.records` according to batch processing time | Keeps the interval between polls within limits |
| Use a compatible cooperative assignor | Reduces the number of partitions revoked during an assignment change |
| Use static membership when appropriate | Reduces rebalances from brief restarts of the same instance |
| Stabilize consumer count and avoid frequent restarts | Limits continuous membership churn |
| Align group and assignor configuration | Prevents incompatible consumers in the same group |
| Monitor heartbeats, polls, lag, and rebalance duration | Detects root causes before prolonged impact |

Do not try to prevent every rebalance. Rebalancing is Kafka's recovery and load-distribution mechanism. The goal is to reduce abnormal rebalances while ensuring the group still responds properly when a consumer genuinely fails or needs to scale.

## 10. Diagnosing Frequent Rebalances

When logs show a group continuously rebalancing, check in order:

1. Inspect consumer logs for leave-group reasons: heartbeat timeout, poll interval exceeded, explicit leave, duplicate member ID, or coordinator connection errors.
2. Measure listener processing times and batch sizes. Compare high percentiles against `max.poll.interval.ms`.
3. Inspect CPU, garbage collection, network, and database/API wait times on each instance.
4. Check pod/VM restart counts and readiness/liveness probes; continuous restarts cause constant membership churn.
5. Check whether subscriptions, regex topic patterns, or partition count changes are altering assignments.
6. Verify all consumers in the group use compatible assignors and group protocols.
7. Check whether revoke/assign callbacks are blocking or throwing exceptions.

You can use Kafka administration tools to inspect group members, consumer IDs, partition assignments, and lag. With Spring Kafka, adding structured logs inside rebalance callbacks helps correlate revoke/assign events with deployment timestamps and processing conditions.

## 11. Common Misconceptions

1. **Assuming rebalances only happen when a consumer dies.** A new consumer joining, subscription changes, adding partitions, or exceeding `max.poll.interval.ms` can also trigger a rebalance.
2. **Assuming cooperative rebalancing eliminates downtime completely.** It only reduces the scope of partitions that must be revoked; the group may still require one or more transition rounds.
3. **Sharing the same `group.instance.id` across multiple consumers.** Static member IDs must be unique per consumer instance in the group.
4. **Increasing `session.timeout.ms` to fix every rebalance.** This setting only changes the time to detect missed heartbeats; it does not resolve slow listener processing or hung consumers.
5. **Doing heavy work in revoke/assign callbacks.** Blocking callbacks can prolong the rebalance.
6. **Assuming an already-processed record will definitely not be reprocessed.** If the offset has not been committed, a new consumer may read the record again.
7. **Trying to preserve assignments at all costs.** Rebalancing is essential for the group to recover when consumers are lost or load shifts.

Rebalancing is a normal part of the consumer group lifecycle. By understanding its triggers, the difference between eager and cooperative assignment, and how Spring Kafka manages callbacks and offsets, you can reduce unnecessary disruptions while preserving the resilience of your messaging system.

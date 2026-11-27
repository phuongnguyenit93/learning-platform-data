# Partitioning Differences Between Kafka and RabbitMQ

Partitioning divides a data stream into multiple parts to increase parallel processing capacity and keep related events in the same processing unit. In Spring Cloud Stream, an application can declare a partition key and partition count using a common model. However, Kafka and RabbitMQ implement this model in two different ways.

Kafka has partitions as a native storage and distribution structure of a topic. Each partition is its own ordered log; a consumer group distributes partitions across consumers. RabbitMQ does not have native partitions in this sense. The Spring Cloud Stream Rabbit binder simulates partitioning by creating one queue per partition and binding those queues to the destination exchange. Therefore, scaling, load distribution, consumer management, and ordering guarantees differ between the two brokers.

This lesson focuses on the partition semantics of each broker, how Spring Cloud Stream selects partitions by key, producer and consumer configuration, running multiple instances, changing partition counts, error handling, and testing. The goal is to help choose a model suited to your application's ordering, throughput, and scaling requirements.

## Learning Objectives

After this lesson, you will be able to:

- Explain partitions in Kafka and how the RabbitMQ binder simulates partitions.
- Distinguish between topic partition, consumer group, exchange, queue, and routing.
- Choose a stable partition key so events for the same entity land in the same partition.
- Configure partition key, partition count, and consumer instances in Spring Cloud Stream.
- Understand how Kafka rebalances partitions and how the Rabbit binder binds instances to queues.
- Analyze the impact of partition count on ordering, load, latency, and scalability.
- Test key distribution, ordering, and behavior when an instance fails.

## 1. Why Is Partitioning Needed?

Suppose an e-commerce system emits order events. An order can generate events such as:

- `OrderCreated`: the order is created.
- `PaymentAuthorized`: payment is authorized.
- `OrderPacked`: the order has been packed.
- `OrderShipped`: the order is handed over to the carrier.

Events for the same order typically need to be processed in business order. If `OrderShipped` is processed before `OrderCreated`, the order state can become corrupted. At the same time, the system handles thousands of orders per second, so a single consumer may not have enough capacity.

Partitioning addresses two requirements:

1. **Parallelization**: split the data stream into multiple partitions so multiple consumers process concurrently.
2. **Per-key affinity**: events sharing the same key, such as `orderId`, are routed to the same partition so they can be processed sequentially within that partition's scope.

Partitioning does not create global ordering by itself. It creates independent ordering domains. If a system has six partitions, ordering among events within a single partition can be preserved by the broker's mechanism; there is no overall ordering across all six partitions.

## 2. Spring Cloud Stream's Common Partitioning Model

Spring Cloud Stream provides a shared abstraction for partitioning, whether the broker supports it natively or not. This model has two sides:

- **Producer** determines each message's partition key and computes the target partition.
- **Consumer** is configured to receive the appropriate partition or group of partitions corresponding to the application instance.

An output binding can configure the partition key in one of two ways:

- `partitionKeyExpression`: a SpEL expression extracting the key from the message.
- `partitionKeyExtractorName`: the name of a bean implementing `PartitionKeyExtractorStrategy`.

These two key-extraction methods are mutually exclusive. Once the key is obtained, the framework selects a partition in the range `0` to `partitionCount - 1`. By default, Spring Cloud Stream uses a calculation based on the key's `hashCode` and `partitionCount`. Partition selection can be customized via `partitionSelectorExpression` or a `PartitionSelectorStrategy` bean.

Common configuration example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.partitioned
          producer:
            partition-key-expression: payload.orderId
            partition-count: 6
~~~

In this example:

- `publishOrder-out-0` is the output binding of the event-emitting function.
- `destination` is the logical destination name that the binder maps to the broker.
- `partition-key-expression` extracts `orderId` from the payload.
- `partition-count` declares the expected number of partitions for the stream.

With `orderId` as the key, events for the same order map to the same partition as long as producers use the same algorithm and partition count. This is the foundation for preserving per-order processing order.

### 2.1. Choosing a Key and Selecting a Partition Are Two Steps

Do not confuse a partition key with a partition ID:

1. **Partition key** is the value representing an entity or data group, such as `customerId` or `orderId`.
2. **Partition selector** turns the key into a specific partition number.

For example, key `order-100` might hash to partition 3 in a six-partition setup. Key `order-101` might be placed into partition 1. The exact outcome depends on the selector algorithm and the partition count.

A key should have these qualities:

- Stable throughout the entity's entire lifecycle.
- Generated identically across all producers emitting to the same stream.
- Sufficiently distributed to prevent one partition from taking excessive load.
- Directly tied to business ordering requirements.

If per-order ordering is needed, use `orderId`. If per-customer ordering is needed, use `customerId`. Do not pick a random key per message because related events will scatter across multiple partitions.

### 2.2. Consumer-Side Configuration

An input binding receiving partitioned data can declare:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.partitioned
          group: order-processor
          consumer:
            partitioned: true
~~~

`partitioned` indicates that the consumer receives data from a partitioned producer. The `instanceIndex` and `instanceCount` properties identify the instance's position in the deployment group when the binder needs to map partitions to instances:

- `instanceCount` is the total number of application instances in the partitioning model.
- `instanceIndex` is the unique index of the instance, starting at `0` and less than `instanceCount`.

For example, three instances have `instanceCount` equal to `3` and `instanceIndex` values `0`, `1`, and `2` respectively. Accurate configuration is critical with binders that lack a native partition-distribution mechanism.

## 3. Native Partitions in Kafka

### 3.1. Topics and Partitions

Kafka organizes data by topic. A topic can have one or more partitions. Each partition is an independently ordered append-only log. New records are appended to the end of the partition log and identified by an offset within that partition.

Key characteristics:

- Ordering is guaranteed within a single partition.
- Each partition has independent offsets.
- A consumer group divides a topic's partitions among its member consumers.
- Within the same consumer group, a partition is assigned to at most one consumer at a time.
- Multiple consumer groups can read the same topic independently with their own offsets.

For example, an `orders` topic has six partitions. Group `order-processor` runs three consumers. Kafka can assign two partitions to each consumer. If you scale up to six consumers, each consumer can receive one partition. If you run ten consumers, at least four consumers will have no partitions to read from in that group.

### 3.2. Producer Partition Selection

The producer can select a partition by key. With Spring Cloud Stream, `partitionKeyExpression` determines the key at the framework abstraction layer; the partition selector decides the partition index. The Kafka binder then sends the record to the corresponding partition.

Complete configuration example:

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
          producer:
            partition-key-expression: payload.orderId
            partition-count: 6
~~~

The Kafka binder uses `partitionCount` as a hint when determining partitioning; the topic's actual partition count is also taken into account. If the topic already has more partitions than the configured `partitionCount`, the binder uses the larger number. Therefore, create topics with an appropriate partition count and verify topic metadata during deployment.

The partition key at the Spring Cloud Stream layer and Kafka's record key are both involved in routing, but they should not automatically be treated as the exact same concept in every configuration. If an application needs Kafka's record key for log compaction or downstream consumers, configure and test the record key explicitly according to Kafka binder capabilities.

### 3.3. Consumer Groups and Rebalancing

In default mode, Kafka manages partition distribution among consumers in the same group via group coordination and rebalancing. When a consumer joins, leaves, or loses connectivity, Kafka can redistribute partitions.

Example:

~~~text
Topic orders: P0 P1 P2 P3 P4 P5

Group order-processor, 3 consumers:
Consumer A <- P0, P1
Consumer B <- P2, P3
Consumer C <- P4, P5
~~~

When Consumer B stops, Kafka triggers a rebalance and reassigns P2 and P3 to the remaining consumers according to the assignor and group state.

With the Kafka binder, `autoRebalanceEnabled` defaults to `true`. When enabled, Kafka distributes partitions automatically and consumer-side `instanceIndex`/`instanceCount` are usually not needed. If `autoRebalanceEnabled` is disabled, the binder can use `instanceCount` and `instanceIndex` to determine which partitions belong to each instance; in that case, there must be at least as many partitions as instances and indices must be configured accurately.

Rebalancing can pause consumption temporarily. Applications must handle shutdowns, offset commits, and in-flight work carefully to avoid duplicate processing or prolonged recovery times.

### 3.4. Parallelism and Ordering Limits

Within a consumer group, the number of consumers actively receiving data cannot exceed the number of assigned partitions. The partition count therefore sets the parallelism ceiling at the group level.

If six partitions are divided among three consumers, each consumer can process two partitions. However, if each consumer processes messages concurrently across multiple threads, task completion order may differ from read order. When business ordering must be preserved, limit processing concurrency per partition or use a suitable serialization mechanism.

There is no overall ordering across partitions. If an order has events that must be sequential, all events for that order must use the same `orderId` as the key and the same partitioning rule.

## 4. RabbitMQ Has No Native Partitions

### 4.1. Exchanges and Queues

RabbitMQ uses exchanges to route messages to queues. Queues store messages waiting for consumers to receive and acknowledge them. An exchange is not a partitioned log like a Kafka topic.

RabbitMQ does not support native partitioning in the topic-partition sense. The Spring Cloud Stream RabbitMQ binder provides partitioning by creating one queue per partition and binding those queues to the destination exchange.

This can be visualized as:

~~~text
Producer
   |
   v
Topic exchange: orders.partitioned
   |             |             |
   v             v             v
Queue P0       Queue P1       Queue P2
   |             |             |
Consumer 0    Consumer 1    Consumer 2
~~~

The producer computes the partition from the key. The binder routes the message to the queue corresponding to that partition. Each consumer instance is configured to read from the queue of its assigned partition.

The crucial point is that a partition in the Rabbit binder is a construct built by the binder on top of queues and bindings. It does not turn RabbitMQ into Kafka; storage, acknowledgment, redelivery, and scaling semantics remain RabbitMQ semantics.

### 4.2. RabbitMQ Producer Configuration

Example partitioned producer configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.partitioned
          producer:
            partitioned: true
            partition-key-expression: payload.orderId
            partition-count: 3
            required-groups:
              - order-processor
~~~

In the Rabbit binder:

- `partitioned: true` enables the binder's partitioning mechanism.
- `partition-key-expression` extracts the key from the message.
- `partition-count` specifies the number of partitioned queues to create.
- `required-groups` declares consumer groups that must be provisioned even before consumers are deployed.

`required-groups` is especially important with RabbitMQ. If a producer sends messages to a partitioned exchange before the corresponding group's queues are created, messages may not be retained for a consumer deployed later. Declaring `required-groups` instructs the binder to pre-create the necessary queues when the producer is deployed.

### 4.3. RabbitMQ Consumer Configuration

The consumer needs to enable `partitioned` and specify the instance index:

~~~yaml
spring:
  cloud:
    stream:
      instance-count: 3
      instance-index: 0
      bindings:
        processOrder-in-0:
          destination: orders.partitioned
          group: order-processor
          consumer:
            partitioned: true
            instance-index: 0
~~~

With three partitions, instances must be deployed with distinct indices:

| Instance | `instance-count` | `instance-index` | Assigned Partitioned Queue |
|---|---:|---:|---|
| A | 3 | 0 | P0 |
| B | 3 | 1 | P1 |
| C | 3 | 2 | P2 |

The `instance-index` value must be unique across instances and lie in the range `0` to `instance-count - 1`. With the Rabbit binder, this configuration tells the binder which partitioned queue the instance will consume.

The Rabbit binder does not support dynamic scaling for the partitioned consumer model the way Kafka group rebalancing does. There must be at least one consumer per partition, and instances must be deployed with matching indices. If changing the number of instances or partitions, plan topology changes and synchronized configuration updates carefully.

## 5. Comparing Kafka and RabbitMQ

| Aspect | Kafka | RabbitMQ Binder |
|---|---|---|
| Native partitions | Yes, inside topics | No; binder simulates them using queues |
| Core structures | Topic, partition, log, offset | Exchange, queue, binding, acknowledgment |
| Key-based routing | Selects a topic partition | Selects a partitioned queue bound to an exchange |
| Consumer progress | Offset per partition and group | Message state in queue and acknowledgment |
| Consumer distribution | Kafka group coordinator and rebalancing | Instance index maps to partitioned queues |
| Scaling consumers | Can add/remove consumers; Kafka rebalances | Does not support dynamic scaling of partitioned consumers; requires instances per partition |
| Re-reading / replay | Can seek/re-read offsets within retention | Acknowledged messages are typically removed from the queue; no equivalent offset log |
| Ordering | Within a single partition | Per queue; concurrent processing/redelivery can affect completion order |
| Provisioning | Topic and partitions | Exchange, queues, and bindings |
| Special configuration | `autoRebalanceEnabled`, consumer group, and topic | `partitioned`, `instanceIndex`, `requiredGroups` |

Spring Cloud Stream allows sharing how keys and partition counts are declared, but it does not make the brokers behave identically. When switching binders, review topology, replay capability, consumer lifecycle, and operations.

## 6. Choosing the Right Partition Key

### 6.1. Key by Business Entity

If per-order ordering is required, choose `orderId`:

~~~java
@Bean
Function<OrderCommand, OrderEvent> toOrderEvent() {
    return command -> new OrderEvent(
            command.orderId(), command.type(), command.createdAt());
}
~~~

On the output binding, use:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        toOrderEvent-out-0:
          destination: orders.partitioned
          producer:
            partition-key-expression: payload.orderId
            partition-count: 6
~~~

If per-customer ordering is required, replace the key with `customerId`. The key must represent the ordering domain to protect. A system may need two separate streams if it requires ordering by `orderId` in one flow and by `customerId` in another; a single partition key cannot simultaneously guarantee every independent ordering domain.

### 6.2. Avoiding Hot Partitions

If one key accounts for most of the traffic, every message for that key concentrates on one partition. For example, if all events from a major customer share the same `customerId`, the corresponding partition may overload while other partitions sit idle.

This is a trade-off between ordering and load distribution:

- Too broad a key can scatter related events, losing per-entity ordering.
- Too concentrated a key can create a hot partition.
- Random keys spread load better but lose affinity.

Measure real key distribution, per-partition throughput, consumer lag, or queue depth before settling on a strategy. If one entity produces excessive traffic, revisit the ordering requirement or split the processing domain using a different business model.

### 6.3. Hashing and Stability

By default, Spring Cloud Stream selects partitions using a calculation based on the key's `hashCode` and `partitionCount`. If producers run across multiple applications or languages, ensure key generation and selector behavior stay consistent. Do not use Java objects whose `hashCode` relies on identity or values unstable across processes.

With normalized `String`, UUID, or integer keys, hashing behavior is easier to control. If another algorithm is needed, use `partitionSelectorExpression` or `PartitionSelectorStrategy` and implement it consistently across all producers.

## 7. Choosing Partition Count and Changing Topology

The partition count affects throughput, parallelism, memory, file handles, metadata, and operational cost. More partitions do not always make a system faster.

When choosing a partition count, consider:

- Expected write and read throughput.
- The number of consumer instances that can run concurrently.
- Key cardinality and data distribution.
- Ordering requirements and per-consumer state size.
- Broker resource capacity and rebalance duration.
- Near-term future partition needs.

### 7.1. Impact of Increasing Partitions

With the default `hashCode(key) % partitionCount` selection, changing `partitionCount` can remap many keys to different partitions. This can break the assumption that all events for an entity always travel through the same partition throughout its lifecycle.

For example, a key previously routed to partition 1 with four partitions may land on a different partition after scaling up to six partitions. If older events remain in the old partition while newer events enter the new partition, two streams may be processed concurrently and finish out of order.

With Kafka, increasing a topic's partitions does not automatically move existing records. With the Rabbit binder, changing the partition count may require creating or modifying partitioned queues and bindings. Therefore, changing the partition count requires a migration plan covering producers, consumers, and existing data.

### 7.2. Safe Change Strategies

Some options:

1. Create a new versioned destination with the new partition count, migrate producers in phases, and have consumers process both streams during the transition window.
2. Pause or throttle producers, wait for the old backlog to drain, then update the topology and restart with the new configuration.
3. Use a stable partitioning algorithm that minimizes remapping, if required and tested by your system.

Do not change the partition count directly in production without evaluating key mapping, existing backlog, and processing order.

## 8. Consumer Concurrency and Scalability

### 8.1. Kafka

Within a Kafka consumer group, each partition is assigned to one consumer at a time. If a topic has six partitions:

- One consumer can read all six partitions.
- Three consumers can split them, two partitions per consumer.
- Six consumers can each receive one partition.
- Ten consumers will leave extra consumers without any assigned partitions.

Kafka can rebalance when the consumer count changes. This supports dynamic scaling, though rebalancing can cause temporary pauses and should be monitored.

If consumer concurrency inside one instance exceeds its assigned partition count, not every thread will receive its own partition. At the same time, parallel processing within one partition can alter completion order. Distinguish between consumer count, processing thread count, and partition count.

### 8.2. RabbitMQ

With the partitioned Rabbit binder, each partition is a queue. Each consumer instance is bound to queues according to its instance index. The binder does not dynamically redistribute partitioned queues to new instances the way Kafka's dynamic rebalancing does.

If there are three partitions, deploy three instances with indices 0, 1, and 2. If instance 1 stops, queue P1 can accumulate messages until a matching consumer becomes active again. Monitor queue depth and plan recovery of instances with the exact missing index.

RabbitMQ allows multiple consumers on a queue in standard patterns, but with partitioning, concurrency must be controlled to preserve business ordering. If multiple consumers process the same queue concurrently, receive order and completion order can diverge, especially with prefetching, redeliveries, or uneven processing times.

### 8.3. Choosing a Broker by Scaling Model

Kafka is typically suited when you need an event log with retention, offset-based replay, and consumer group scaling by partition. RabbitMQ is typically suited for message routing via exchanges/queues, acknowledgments, and queue-based work distribution. The Rabbit binder can still provide partition affinity, but requires tighter management of instance indices and queue topology.

Do not choose RabbitMQ merely because it supports partitioned configuration and assume it scales identically to Kafka. Choose based on the storage, delivery, and operational semantics your system actually requires.

## 9. Processing Order and Delivery Guarantees

A partition key only routes related messages to the same partition. It does not guarantee that all side effects complete in order if the consumer processes asynchronously or across multiple parallel threads.

To preserve ordering:

- Use a stable entity-based key.
- Do not vary the partition selector across producers.
- Limit parallel processing within the same partition or queue when strict ordering is needed.
- Acknowledge messages only after processing satisfies business conditions.
- Design idempotent consumers to handle redeliveries.
- Do not rely on global ordering across partitions.

### 9.1. Kafka Offsets

Kafka tracks consumption progress using per-partition offsets. A consumer group commits offsets to record the processed position. If offsets are committed before business work finishes, work can be lost if the consumer crashes. If committed after completion but a crash occurs before committing, messages may be re-read.

Therefore, coordinate commit mode, acknowledgments, and transactions according to binder configuration. Idempotency remains essential whenever the same record might be reprocessed.

### 9.2. RabbitMQ Acknowledgments

A RabbitMQ consumer acknowledges a message after processing. If the consumer dies before acknowledging, the message may be requeued and redelivered. If processing in parallel or with multiple consumers on the queue, completion order can change.

Do not treat a partitioned queue as an offset-based log you can seek arbitrarily. Once a message is acknowledged and removed from the queue, replay depends on dead-letter queues, publishers, or application-level storage.

### 9.3. Exactly-Once and Idempotency

No partition automatically creates an end-to-end exactly-once guarantee for business logic. Kafka can support transactions and exact-within-Kafka semantics when configured properly; RabbitMQ has acknowledgments and publisher confirms, yet redelivery scenarios still occur. Whenever a consumer updates a database or calls external services outside the broker, design idempotency, inbox/outbox patterns, or compensating actions.

## 10. Testing Partitioning

Testing should prove three properties:

1. The same key maps to the same partition.
2. Different keys can spread across multiple partitions.
3. Consumers receive the expected assigned slice and scaling/failure behavior matches expectations.

### 10.1. Testing Partition Selection Logic

If using a custom selector, test the algorithm in isolation:

~~~java
class CustomerPartitionSelector implements PartitionSelectorStrategy {

    @Override
    public int selectPartition(Object key, int partitionCount) {
        String customerId = String.valueOf(key);
        return Math.floorMod(customerId.hashCode(), partitionCount);
    }
}
~~~

This example uses `floorMod` so the result always stays within valid bounds even if `hashCode` is negative. If using the framework's default selector, verify results against your library version and avoid assuming a custom selector is active.

Test:

~~~java
@Test
void sameCustomerUsesSamePartition() {
    CustomerPartitionSelector selector = new CustomerPartitionSelector();

    int first = selector.selectPartition("customer-10", 6);
    int second = selector.selectPartition("customer-10", 6);

    assertThat(first).isEqualTo(second);
}
~~~

### 10.2. Testing Kafka

Integration tests with Kafka should verify:

- The topic has the expected partition count.
- Records with the same key are written to the same partition.
- The consumer group splits partitions as expected.
- Rebalancing when instances join or leave.
- Offsets and reprocessing after an abrupt consumer stop.
- Record ordering within the same partition.

The Test Binder can test part of the binding logic and partition headers at the Spring layer, but it does not replace real Kafka broker tests for partition assignment, offsets, and rebalancing.

### 10.3. Testing RabbitMQ

Integration tests with RabbitMQ should verify:

- The destination exchange is created with the expected type.
- Dedicated queues exist for each required partition and group.
- Routing keys/partition keys deliver messages to the right queue.
- Each instance index consumes from the right queue.
- `required-groups` pre-creates queues when consumers are not yet deployed.
- Queues buffer messages and recover when an instance stops.
- Acknowledgments, redeliveries, and ordering under real concurrency.

Do not just check that a message arrives in a queue. Send many different keys to verify distribution, and send multiple messages with the same key to verify affinity.

## 11. Operations and Observability

### 11.1. Kafka Metrics

Monitor:

- Partition count and leader/replica status.
- Consumer lag by group and partition.
- Write/read rates per partition.
- Rebalance count and rebalance duration.
- Producer errors, retries, and offset commit errors.
- Load skew across partitions to detect hot partitions.

If one partition shows steadily rising lag while others remain stable, inspect key distribution, anomalous payloads, or slow consumer processing.

### 11.2. RabbitMQ Metrics

Monitor:

- Number of partitioned queues created per destination/group.
- Queue depth and age of the oldest message.
- Consumer count per queue.
- Unacknowledged messages and redeliveries.
- Publish/consume rates and publisher confirms.
- Queues with zero consumers due to a missing instance index.

If queue P2 has a large backlog while P0 and P1 are empty, keys may be skewed or the corresponding consumer may be down. Check instance indices and key mappings before arbitrarily adding consumers.

### 11.3. Multi-Instance Deployment

With Kafka, deploy multiple consumers in the same group and let Kafka rebalance when using default mode. With the partitioned Rabbit binder, supply the right instance count and index to each instance; avoid having two instances share the same index when they are expected to handle independent partitions.

During rolling updates, account for consumer group departure, rebalancing, queue backlog, and in-flight message completion. Maintain health checks, graceful shutdowns, and alerts for partitions/queues with no active consumers.

## 12. Common Design Mistakes

1. **Choosing a random key per message**: events of the same entity scatter and lose affinity. Use a stable key such as `orderId`.
2. **Using an overly concentrated key**: one partition becomes a hot partition. Measure key distribution and review the ordering domain to protect.
3. **Assuming partitions provide global ordering**: ordering is only guaranteed within a partition/queue under proper processing conditions. Design ordering per entity.
4. **Scaling Kafka consumers past the partition count expecting all to work**: excess consumers receive no partitions. Choose an appropriate partition count and concurrency.
5. **Treating the Rabbit binder like Kafka**: RabbitMQ does not have native log partitions. Understand queue-per-partition and manage topology accordingly.
6. **Missing `instanceIndex` or `instanceCount` on RabbitMQ**: consumers may fail to read the right partitioned queues. Configure unique indices per instance.
7. **Not provisioning `required-groups`**: messages can be lost before consumer queues are created. Declare `required-groups` when consumer queues must exist upfront.
8. **Assuming Rabbit partitioned consumers dynamically scale**: the binder requires instance index management and at least one consumer per partition. Plan synchronized deployments.
9. **Arbitrarily increasing partition count**: keys may remap to new partitions and disrupt per-entity ordering. Have a migration plan.
10. **Uncontrolled parallel processing within a single partition**: task completion order can differ from receive order. Limit concurrency when business rules require it.
11. **Testing only with the Test Binder**: fails to verify real broker characteristics. Add integration tests with real Kafka or RabbitMQ.
12. **Treating partitioning as an exactly-once guarantee**: redeliveries and crashes can still cause duplicate processing. Use event IDs and idempotency.

## 13. Selection and Rollout Checklist

When designing partitioning for an event stream, follow this sequence:

1. Identify the entity requiring ordering: order, customer, account, or device.
2. Choose a stable partition key matching that entity.
3. Estimate throughput, consumer count, and required partition count.
4. Determine whether the broker has native partitions or relies on binder queue simulation.
5. Configure `partitionKeyExpression` or extractor and `partitionCount`.
6. Configure consumer group, `partitioned`, `instanceIndex`, and `instanceCount` per the binder.
7. For RabbitMQ, decide on `required-groups` and verify provisioned queues/bindings.
8. For Kafka, check topic partition count, auto-rebalance, and group assignment.
9. Test key affinity, load distribution, ordering, redelivery, and instance failure scenarios.
10. Set up dashboards and alerts for lag, queue depth, rebalancing, and hot partitions.
11. Plan ahead before changing partition count or selectors.

## Conclusion

Kafka has native partitions inside topics: each partition is an independently ordered log, consumer groups divide partitions among consumers, and Kafka can rebalance when the consumer count changes. RabbitMQ has no native partitions; the Rabbit binder simulates partitions using dedicated queues per partition bound to the destination exchange. RabbitMQ consumers must be mapped to queues by instance index, and this topology does not support dynamic scaling like Kafka.

Spring Cloud Stream provides a shared way to declare partition keys and partition counts, yet applications must still respect broker semantics. Choosing stable keys, controlling hot partitions, managing instance counts, preserving processing order, and planning topology changes are essential so partitioning improves throughput without corrupting business data.

## References

- [Spring Cloud Stream — Partitioning](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-partitioning.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — RabbitMQ Binder: Partitioning](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html)

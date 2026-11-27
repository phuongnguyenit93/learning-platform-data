# Partitioning to Group Messages by Business Key

In an event-processing system, many related messages need to be processed by the same stream or the same instance to preserve state and business ordering. For example, order creation, payment, update, and cancellation events for the same order should go to the same partition. If they are scattered arbitrarily, two consumers could update the same order concurrently or complete steps in an unintended order.

Spring Cloud Stream provides a partitioning abstraction so that a producer selects a partition based on each message's key and consumers receive partitions in a way that fits the binder. The key is usually a stable business identifier such as `orderId`, `accountId`, `customerId`, or `sensorId`. With Kafka, a partition is a native topic structure. With RabbitMQ, the binder can simulate partitions using separate queues. With Pulsar, partitioned topics and key-based routing have Pulsar's own mechanisms. Both the common abstraction and how the binder implements it must be understood in order to configure it properly.

## 1. Why Is Key-Based Partitioning Needed?

Partitioning divides data into multiple independent parts. The producer computes a key for the message and then selects the target partition. Messages with the same key are mapped to the same partition using a consistent algorithm. A consumer group distributes the partitions across multiple consumer instances to increase parallel processing capacity.

For example, with order events:

| Message | Business Key | Partition |
|---|---|---|
| OrderCreated ORD-1001 | ORD-1001 | 2 |
| PaymentReceived ORD-1001 | ORD-1001 | 2 |
| OrderShipped ORD-1001 | ORD-1001 | 2 |
| OrderCreated ORD-1002 | ORD-1002 | 4 |
| PaymentReceived ORD-1002 | ORD-1002 | 4 |

The events for ORD-1001 all go into partition 2; the events for ORD-1002 all go into partition 4. Two partitions can be processed in parallel, while events for the same key are grouped into the same partitioning unit.

Partitioning is useful when:

- Events of the same aggregate or business entity must preserve ordering.
- A consumer maintains local state per key, such as the total balance of an account or the state of an order.
- Throughput needs to be scaled with multiple partitions and consumers.
- Multiple instances must be prevented from updating the same per-key state concurrently.

Partitioning does not automatically guarantee exactly-once processing, does not replace idempotency, and does not provide global ordering across partitions. It only determines how data is grouped and work is distributed. Applications still need to handle retries, redeliveries, transactions, and duplicates according to business requirements.

## 2. Distinguishing Partition, Consumer Group, and Instance

These three concepts are related but not synonymous:

| Concept | Role |
|---|---|
| Partition | A part of a destination that maintains its own ordered data stream according to the broker's capabilities |
| Consumer group | A group of consumers sharing data consumption; each group maintains its own consumption progress |
| Consumer instance | A running application process/replica that receives one or more partitions |

In Kafka, each partition in a consumer group is assigned to at most one consumer in that group at a time. One consumer can receive multiple partitions. If the number of active consumers exceeds the number of partitions, some consumers will have no partitions to read from. If the number of partitions exceeds the number of consumers, one consumer can receive multiple partitions.

Messages with the same key are grouped into the same partition; the consumer instance owning that partition can change after a rebalance or upon redeployment. Therefore, partitioning keeps the data grouped in the same read stream, but does not guarantee that a specific process will own that key for the entire application lifecycle.

Different consumer groups read independently. For example, both the `order-projection` group and the `audit-service` group can receive the same event, with each group maintaining its own progress. Within the same group, consumers split the data to scale processing; they do not receive independent copies of every message.

With RabbitMQ and binders that simulate partitions with queues, how queues are assigned to instances differs from Kafka's mechanism. With Pulsar, the subscription type and partitioned topic determine how distribution works. Do not apply a single consumer assignment model to every broker just because both use Spring Cloud Stream.

## 3. Both Sides Must Configure Partitioning

A partitioned processing scenario requires configuring both the producer and the consumer:

1. The producer extracts the partition key from the message and determines the target partition.
2. The broker/binder stores or routes the message to the corresponding partition.
3. The consumer group receives the partitions and assigns them to instances.
4. The consumer processes data in the assigned partition, preserving ordering and state as designed.

If the producer only sends a key without enabling partitioning, or the consumer does not read the right partitions, business-level grouping will not achieve its goal. If producers do not agree on the partition count or partition selection algorithm, the same key may be routed to different partitions. Consumers must also be configured with the right instance count and partition assignment mechanism so no partition is missed.

## 4. Choosing a Partition Key from Business Data

In Spring Cloud Stream, a producer can use the `partitionKeyExpression` property to extract a key using SpEL. The expression is evaluated against the outbound message. For example:

    spring:
      cloud:
        stream:
          bindings:
            publishOrder-out-0:
              destination: orders.events
              producer:
                partition-key-expression: payload.orderId
                partition-count: 6
          instance-count: 3

If the message has the payload:

    public record OrderCreated(
        String eventId,
        String orderId,
        long total
    ) {}

then the expression `payload.orderId` takes `orderId` as the partition key. A payment or shipping event must also use the same `orderId` key if they must be grouped with the other events of that order.

If an output binding accepts multiple DTOs with different structures, do not assume every payload has an `orderId` property. You can standardize the key in a common envelope, such as `aggregateId`, or set a standard header on every message:

    partition-key-expression: headers['aggregateId']

Producers of `OrderCreated`, `PaymentReceived`, and `OrderShipped` must all attach the same `aggregateId` for the same order. This keeps a consistent key convention even when each event's payload differs.

When the producer application is deployed as multiple replicas, set `spring.cloud.stream.instanceCount` to the total number of replicas as required by Spring Cloud Stream. The configuration example above sets `instance-count` to 3 for three producer instances. When running standalone, each instance must receive the proper deployment information; environments such as Spring Cloud Data Flow can supply these values automatically.

The key can be extracted from a header:

    partition-key-expression: headers['accountId']

Only use a header if the producer always attaches that header, its data type is stable, and the consumer/binder preserves the required metadata. If the key is part of the business contract, put it in the payload or establish a clearly documented header convention.

A good key should have these characteristics:

- Stable throughout the lifecycle of the aggregate.
- Present on every event type that needs to be grouped together.
- Distributed evenly enough across partitions.
- Free of unnecessary sensitive data.
- Independent of object identity or random values regenerated on each send.

For example, `orderId` is suitable for an order event stream; `accountId` is suitable for a balance update stream; `sensorId` is suitable for a series of readings from the same sensor. Using a timestamp or a new UUID per message usually scatters related messages because each message has a different key.

### Checking for Missing Keys

If the partition key is empty or null, the message may fall into the same default partition, fail during partition calculation, or cause an unintended load distribution depending on the binder. Validate the key before publishing:

    public boolean publish(OrderCreated event) {
        if (event.orderId() == null || event.orderId().isBlank()) {
            throw new IllegalArgumentException("orderId is required for partitioning");
        }
        return streamBridge.send("publishOrder-out-0", event);
    }

Do not use a shared default value for all invalid messages, as that can create a hot partition. If there is no valid business key, reject the message or route it to an error flow according to policy.

## 5. How Spring Cloud Stream Selects a Partition

A partitioned producer needs to configure exactly one of these two properties:

- `partitionKeyExpression`: a SpEL expression that extracts the key from the outbound message.
- `partitionKeyExtractorName`: the bean name implementing `PartitionKeyExtractorStrategy` to extract the key in Java.

At the same time, `partitionCount` must be greater than 1. The two key-extraction approaches are mutually exclusive; do not configure both for the same binding.

After obtaining the key, Spring Cloud Stream selects a partition in the range from `0` to `partitionCount - 1`. By default, the algorithm is based on the key's `hashCode` divided by `partitionCount`. This can be customized with `partitionSelectorExpression` or a `PartitionSelectorStrategy` bean.

Example using a partition selector expression:

    spring:
      cloud:
        stream:
          bindings:
            publishOrder-out-0:
              destination: orders.events
              producer:
                partition-key-expression: payload.orderId
                partition-selector-expression: key.hashCode() % 6
                partition-count: 6

In most cases, the default selector is sufficient. Only customize it when there is a clear requirement for the distribution algorithm or when compatibility with another system is needed. Producers and consumers do not automatically negotiate the algorithm; they must share the same understanding of how partitioning is implemented.

The default algorithm relies on the Java key object's hash function. For Java strings, `hashCode` produces a stable result based on string content; for custom objects, do not rely on the default identity-based implementation if messages are recreated in another process. If there are producers written in multiple languages or partitioning must be JVM-independent, publish a shared hash/selector algorithm and test the same set of keys across all producers. Do not assume different languages produce the same partition just because the key string is identical.

### Using PartitionKeyExtractorStrategy

If the key needs to combine multiple fields or requires rules more complex than SpEL, you can register a bean implementing `PartitionKeyExtractorStrategy`:

    @Bean
    PartitionKeyExtractorStrategy orderKeyExtractor() {
        return message -> {
            OrderCreated event = (OrderCreated) message.getPayload();
            return event.orderId();
        };
    }

Then select the bean in configuration:

    spring:
      cloud:
        stream:
          bindings:
            publishOrder-out-0:
              destination: orders.events
              producer:
                partition-key-extractor-name: orderKeyExtractor
                partition-count: 6

If there are multiple beans of the same type, explicitly specify the extractor name. Do not declare both `partition-key-expression` and `partition-key-extractor-name` on the same binding.

## 6. Choosing the Number of Partitions

`partitionCount` determines the number of partitions the producer abstraction uses to select a target. The value must be greater than 1 when partitioning is enabled. With Kafka, `partitionCount` is treated as a hint; if the actual partition count of the topic is greater than the configured value, the actual count will be used according to binder rules. Inspect the existing topic and its actual partition count rather than relying solely on YAML.

Choosing a partition count requires considering:

- Expected throughput and message size.
- The number of consumer instances that can run concurrently.
- The number of business keys and their distribution.
- Broker file, metadata, replication, and management overhead.
- Future load growth needs.
- Per-key ordering requirements.

For example, suppose there are 6 partitions and 3 consumer instances. If each instance can receive 2 partitions, all 6 partitions have a consumer processing them. If there are only 2 partitions, at most 2 consumers in a group can actively process those partitions at the same time; the remaining instance will have no partition.

Do not create an excessively large number of partitions before there is a need. Each partition adds management overhead and can affect rebalance, recovery, and storage times. Conversely, too few partitions limit parallelism even when the application has many instances.

### Changing the Partition Count Can Change Where a Key Lands

With a modulo-hash algorithm, a key's partition depends on the partition count. When increasing the number of partitions, many keys may map to new partitions. Older messages remain in the old partition, while newer messages for the same key may go to a different partition. At that point, there is no longer a single read order across the key's entire history.

Therefore, changing the partition count is an operational change that affects ordering. Before increasing it, evaluate:

- Does the consumer require ordering across the entire history of an aggregate?
- Can producers be stopped to drain old data before switching over?
- Should a versioned destination be created and data migrated through a controlled process?
- Do state stores or projections need to be rebuilt?

Do not arbitrarily increase the partition count just to address lag if the business flow depends on per-key ordering.

## 7. Configuring Consumers by Binder

Spring Cloud Stream provides the `consumer.partitioned` property to indicate that an input binding receives partitioned data. The `instanceCount` and `instanceIndex` properties specify the total number of instances and the index of the current instance for binders where the application maps partitions explicitly. The following example illustrates partition-aware consumer mode requiring an instance index, commonly seen with binders without native partitions such as RabbitMQ; it does not apply verbatim to Kafka with default auto-rebalance.

Configuration example for a partition-aware consumer with three instances:

    spring:
      cloud:
        function:
          definition: updateOrder
        stream:
          instance-count: 3
          instance-index: 0
          bindings:
            updateOrder-in-0:
              destination: orders.events
              group: order-projection
              consumer:
                partitioned: true

Each replica must have the same `instance-count` and a unique `instance-index` in the range from `0` to `instance-count - 1`. With three replicas, the indices are `0`, `1`, and `2` respectively. Do not let two replicas use the same index if the binder uses that index to assign queues/partitions.

### Kafka

Kafka has native partitions on topics. By default, a Kafka consumer group automatically rebalances and distributes partitions across active consumers. With `autoRebalanceEnabled=true` (the default), `instanceCount` and `instanceIndex` are not required merely for Kafka to distribute partitions.

Consumer group example:

    spring:
      cloud:
        function:
          definition: updateOrder
        stream:
          bindings:
            updateOrder-in-0:
              destination: orders.events
              group: order-projection
              consumer:
                concurrency: 2
          kafka:
            bindings:
              updateOrder-in-0:
                consumer:
                  auto-rebalance-enabled: true

The Kafka binder allows setting `concurrency` per instance; the total number of consumers in the group also depends on the number of replicas. With 3 replicas and concurrency 2, there can be up to 6 consumers in the group. If the topic only has 4 partitions, at most 4 consumers will have assigned partitions; the remaining consumers will be idle.

When `autoRebalanceEnabled=false`, the binder uses `instanceCount` and `instanceIndex` to decide which partitions an instance receives. In that case, you must ensure there are enough partitions for the number of instances and that the indices are configured accurately. Only disable auto-rebalance when there is a specific operational reason and you have tested partition assignment and instance recovery.

### RabbitMQ

RabbitMQ does not have native partitions like Kafka. The Rabbit binder can simulate partitions using multiple queues, where each queue represents a partition. When using this mechanism, the consumer needs to enable `partitioned` and configure `instanceCount`/`instanceIndex` so that each instance receives the assigned queue or set of queues.

Example:

    spring:
      cloud:
        stream:
          instance-count: 3
          instance-index: 0
          bindings:
            updateOrder-in-0:
              destination: orders.events
              group: order-projection
              consumer:
                partitioned: true

The binder provisions partitioned queues according to the configuration and the Rabbit binder version's naming conventions. Verify the actual queues, routing keys, and exchange bindings in the RabbitMQ Management UI. The producer's `partitionCount` configuration must be compatible with the number of provisioned partitions/queues.

### Pulsar

Pulsar supports partitioned topics and key-based routing at the client/broker layer. Subscription type, key-based batching, and distribution mechanisms affect how messages with the same key are processed. When using the Pulsar binder, check which partitioning properties the binder version supports and how `partitionKeyExpression` maps to native keys/partitions.

Do not assume `consumer.partitioned`, `instanceIndex`, and `instanceCount` play the same role across all Pulsar binders. Prefer configuring partitioned topics and key-based routing according to the documentation of the binder/client in use; test with multiple consumers in the same subscription to confirm that messages with the same key are delivered as required.

## 8. Partition Key Is Not Synonymous with Broker Record Key

The partition key in the Spring Cloud Stream abstraction is the value used to select a partition. Whether this value is also written as the broker's native message key depends on the binder and separate configuration.

With Kafka, the record key can be used by Kafka's native partitioner and read back by consumers. If downstream applications or operational tools depend on the record key, configure the message key via the Kafka binder, for example:

    spring:
      cloud:
        stream:
          kafka:
            bindings:
              orders-out-0:
                producer:
                  message-key-expression: headers['orderId']

The producer needs to attach the corresponding `orderId` header to the message before sending. In Kafka binder versions that have the `messageKeyExpression` property, this expression is used to set the Kafka record's key. Check the documentation for the binder version in use because expression evaluation and data types may vary by version. Do not assume `partitionKeyExpression` always means the record key across all binders/configurations.

With RabbitMQ, the routing key controls routing through an exchange; it is not strictly equivalent to Spring Cloud Stream's partition key. With Pulsar, the message key has its own semantics and configuration. When integrating across multiple brokers or multiple languages, clearly document which key is used for partitioning, which key is used for business logic, and which key is stored in the wire message.

## 9. Avoiding Hot Partitions and Skewed Distribution

If one key accounts for most of the traffic, the corresponding partition will receive significantly more load than other partitions. For example, using `tenantId` as the key can cause hotspots if one tenant generates more messages than all other tenants combined. Some common causes include:

- Keys with low cardinality, where many messages share the same value.
- Using a default value for all messages missing a key.
- A single customer or account generating disproportionately high traffic.
- Custom hash/selector logic producing uneven distribution.
- Some partitions having slow consumers or congested downstream dependencies.

Monitor message rate, byte rate, consumer lag, and processing time per partition. If a partition is hot due to business characteristics, increasing the total partition count may not solve the problem because the same key must still go to the same partition to preserve ordering. You may need to split the aggregate, use a sub-key when semantics allow, or handle high-volume groups separately.

Do not add a random suffix to a key solely for load balancing if events for the same aggregate require ordering. That breaks the grouping goal and can cause state to be updated concurrently.

## 10. Ordering, Concurrency, and Business State

Partitioning keeps messages with the same key in the same partition according to the chosen algorithm. The broker may preserve ordering within a partition, but parallel consumer processing can still alter the business completion order.

For example, a consumer receives two events in order:

1. OrderCreated ORD-1001
2. PaymentReceived ORD-1001

If processed concurrently, `PaymentReceived` might finish before `OrderCreated` commits. If business logic requires sequential execution, process sequentially per partition or per aggregate key, use transactions/idempotency, and only ack/commit after the required work is complete.

In Kafka, a partition is assigned to at most one consumer in the same group at a time, yet the application can still offload records to a separate executor and lose completion order. In RabbitMQ, competing consumers on a queue or a large prefetch count can also cause processing order to differ from send order. With Pulsar, the subscription type and key-based routing must be chosen appropriately.

## 11. Complete Example for Order Events

The producer sends events with the same `orderId` to an output binding:

    @Service
    public class OrderPublisher {
        private final StreamBridge streamBridge;

        public OrderPublisher(StreamBridge streamBridge) {
            this.streamBridge = streamBridge;
        }

        public boolean publish(OrderEvent event) {
            if (event.orderId() == null || event.orderId().isBlank()) {
                throw new IllegalArgumentException("orderId is required");
            }
            return streamBridge.send("orders-out-0", event);
        }
    }

Producer configuration:

    spring:
      cloud:
        stream:
          instance-count: 3
          bindings:
            orders-out-0:
              destination: orders.events
              producer:
                partition-key-expression: payload.orderId
                partition-count: 6

Kafka consumer:

    spring:
      cloud:
        function:
          definition: updateOrder
        stream:
          bindings:
            updateOrder-in-0:
              destination: orders.events
              group: order-projection
              consumer:
                concurrency: 2

In this example, the producer uses `orderId` to select one of six partitions. The `order-projection` consumer group reads the topic and Kafka distributes partitions to consumers via the default rebalance mechanism. If three replicas are deployed, each replica can use `concurrency` 2; the number of consumers actually assigned partitions will not exceed the number of assignable partitions.

If switching to RabbitMQ, keep the same business-key concept, but verify how the binder creates partitioned queues and configure `consumer.partitioned` along with `instanceCount`/`instanceIndex`. If switching to Pulsar, check partitioned topics, key-based routing, and subscription types. Do not copy a Kafka configuration verbatim to another binder.

## 12. Testing Partitioning

Tests should verify both key extraction and actual distribution:

- Create multiple messages with the same `orderId` and confirm they are routed to the same partition.
- Create messages with different `orderId` values and check distribution across multiple partitions.
- Send a message missing a key and confirm the producer rejects it or routes it to the error flow according to policy.
- Change the partition count in a test environment to observe how key mapping changes.
- Run multiple consumer instances and confirm each partition is assigned properly per the binder.
- Test rebalancing when an instance stops or restarts.
- Measure receive order and business commit order when consumers process concurrently.
- Test hot partitions using skewed data resembling production.

The Test Binder is useful for verifying function logic and binding configuration within the scope of the application. It does not replace integration tests with a real broker when verifying physical partitions, queue provisioning, key routing, rebalancing, ordering, and consumer assignment. Maintain dedicated tests for Kafka, RabbitMQ, or Pulsar as deployed.

## 13. Operations and Monitoring

In production, monitor:

- Partition count and destination provisioning status.
- Active consumer count in each group/subscription.
- Message rate, byte rate, and consumer lag per partition.
- Processing time and error rate per partition.
- Hot partitions or load imbalances.
- Rebalance count, rebalance duration, and consumers with no assigned partitions.
- Redelivery, retry, and DLQ message counts per partition or per key where observable.

When adding consumers, determine whether the partition count is sufficient to utilize the new instances. When changing the partition count or selector, plan for impacts on ordering, local state, and replay. Record the partition key and partition selection algorithm in the event contract documentation so producers and consumers in other languages can comply.

## 14. Partition Design Checklist

- [ ] A stable business key has been chosen for messages that need to be grouped together.
- [ ] The producer extracts the exact key using `partitionKeyExpression` or `PartitionKeyExtractorStrategy`.
- [ ] Only one key-extraction mechanism is used per binding.
- [ ] `partitionCount` is greater than 1 and matches the actual destination.
- [ ] The default or custom partition selector is documented.
- [ ] The consumer group and partition assignment mechanism match the binder.
- [ ] For RabbitMQ, `partitioned` and `instanceCount`/`instanceIndex` are configured for the required instances.
- [ ] For Kafka, default auto-rebalance and binder-managed assignment cases are understood.
- [ ] For Pulsar, partitioned topics, key routing, and subscription types have been verified.
- [ ] Null keys, skewed distributions, and hot partitions have been tested.
- [ ] The impact of increasing `partitionCount` on key ordering has been evaluated.
- [ ] Tested against a real broker before deployment.

Partitioning by business key groups related events into the same processing unit while allowing different keys to run in parallel. By choosing a stable key, aligning producer/consumer configurations, understanding how the binder maps partitions, and monitoring load per partition, a Spring Cloud Stream application can scale throughput while preserving the consistency required for each aggregate.

## References

- [Spring Cloud Stream — Partitioning](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-partitioning.html)
- [Spring Cloud Stream — Binding properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)

# Customizing PartitionKeyExtractorStrategy and PartitionSelectorStrategy

Spring Cloud Stream supports message partitioning so that events sharing certain characteristics are processed by the same partition. This is useful when a system needs to preserve relative ordering for a business entity, distribute load across multiple instances, or maintain local state for each group of data.

The two strategies handle two distinct steps when sending a message. `PartitionKeyExtractorStrategy` reads the Spring `Message` and extracts the partition key; `PartitionSelectorStrategy` receives that key along with the partition count and decides the target partition index. When a SpEL expression is not expressive enough to describe business rules, you can implement these two interfaces as beans and select them by name in the output binding configuration.

This lesson covers designing stable keys, implementing both strategies, configuring producers and consumers, and key considerations when using Kafka, RabbitMQ, or Pulsar.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish between extracting a partition key and selecting a partition.
- Implement `PartitionKeyExtractorStrategy` and `PartitionSelectorStrategy` in Java.
- Register strategies as Spring beans and select them via `partitionKeyExtractorName` and `partitionSelectorName`.
- Configure `partitionCount` on an output binding and `partitioned` on an input binding when needed.
- Design keys so that events for the same entity are sent to the same partition.
- Understand differences in partitioning across Kafka, RabbitMQ, and Pulsar.
- Test stability, index bounds, and distribution of a partition selector.
- Recognize the impact of changing the partition count or partition selection algorithm.

## 1. Two Steps in the Partitioning Process

When a producer sends a message through an output binding with partitioning enabled, Spring Cloud Stream needs to determine which partition the message belongs to. This process has two steps:

1. **Key extraction:** retrieve information from the message to produce a value representing the data group that must be processed together.
2. **Partition selection:** convert the key into a partition index in the range from `0` to `partitionCount - 1`.

~~~mermaid
flowchart LR
    A["Spring Message<br/>payload + headers"] --> B["PartitionKeyExtractorStrategy"]
    B --> C["Partition key"]
    C --> D["PartitionSelectorStrategy"]
    D --> E["Partition index"]
    E --> F["Binder"]
    F --> G["Broker partition / queue"]
~~~

For example, an order processing system needs all events of the same order to go to the same partition. The extractor can read `tenantId` and `orderId` from the payload to build a composite key. The selector turns that key into an index within the configured number of partitions.

The two interfaces define these contracts:

~~~java
public interface PartitionKeyExtractorStrategy {
    Object extractKey(Message<?> message);
}

public interface PartitionSelectorStrategy {
    int selectPartition(Object key, int partitionCount);
}
~~~

`PartitionKeyExtractorStrategy` receives the entire Spring `Message`, so it can read the payload or headers. `PartitionSelectorStrategy` does not receive the message; it only receives the extracted key and the partition count. Separating these two steps allows changing how keys are extracted without rewriting the distribution algorithm, or changing the distribution algorithm without altering the message data contract.

## 2. When Should You Customize the Strategies?

Spring Cloud Stream supports simple configuration using expressions:

- `partitionKeyExpression` extracts the key from the message using SpEL.
- `partitionSelectorExpression` computes the partition index from the key.

Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders
          producer:
            partitionKeyExpression: payload.orderId
            partitionSelectorExpression: 'T(java.lang.Math).floorMod(#root.hashCode(), 6)'
            partitionCount: 6
~~~

For a simple key like `orderId`, an expression is usually sufficient. However, real-world logic can be more complex:

- The key is built from multiple fields, such as `tenantId` combined with `orderId`.
- Messages arrive in multiple payload shapes, each using a different key field.
- The key resides in a header set by an earlier processing step.
- The key needs normalization before hashing, such as trimming whitespace or normalizing identifiers.
- A custom distribution algorithm is needed to satisfy business rules or maintain compatibility with an existing system.

When expressions become hard to read, hard to test, or need reuse, implement the two strategies as beans.

## 3. PartitionKeyExtractorStrategy: Extracting the Key

`PartitionKeyExtractorStrategy` accepts a `Message<?>` and returns an `Object` as the partition key. The returned value must be stable, non-null, and consistently handled by the selector.

Example order event message:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderCreated(
    String eventId,
    String tenantId,
    String orderId,
    BigDecimal total,
    Instant occurredAt
) {}
~~~

We want every event for an order within the same tenant to go to one partition. We can define a composite key:

~~~java
public record OrderPartitionKey(
    String tenantId,
    String orderId
) {}
~~~

Implementing the extractor:

~~~java
import org.springframework.cloud.stream.binder.PartitionKeyExtractorStrategy;
import org.springframework.messaging.Message;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PartitionStrategyConfiguration {

    @Bean
    PartitionKeyExtractorStrategy orderPartitionKeyExtractor() {
        return message -> {
            if (!(message.getPayload() instanceof OrderCreated event)) {
                throw new IllegalArgumentException(
                    "Payload must be OrderCreated"
                );
            }

            if (event.tenantId() == null || event.tenantId().isBlank()
                    || event.orderId() == null || event.orderId().isBlank()) {
                throw new IllegalArgumentException(
                    "tenantId and orderId are required for partitioning"
                );
            }

            return new OrderPartitionKey(
                event.tenantId(),
                event.orderId()
            );
        };
    }
}
~~~

The extractor reads the payload, checks the type, and validates the required fields before constructing the key. If a message lacks a valid key, throwing an exception surfaces the error clearly at the producer instead of silently routing the message using an inconsistent fallback value.

### Extracting the Key from Headers

If an upstream producer already placed the partition key in a header, the extractor can read that header:

~~~java
@Bean
PartitionKeyExtractorStrategy headerPartitionKeyExtractor() {
    return message -> {
        Object key = message.getHeaders().get("partitionKey");

        if (key == null || key.toString().isBlank()) {
            throw new IllegalArgumentException(
                "Missing partitionKey header"
            );
        }

        return key.toString();
    };
}
~~~

This is useful when multiple payload types follow a shared header contract. However, the header must be set and controlled by a trusted producer. If messages originate externally, validate the header value and do not rely on unverified metadata as the basis for business partitioning.

### Principles for Designing Partition Keys

A good partition key should satisfy:

- **Stability:** the same entity must produce the same key across sends.
- **Meaningfulness:** the key reflects the entity requiring ordering or state locality, such as `orderId`, `accountId`, or `deviceId`.
- **Non-null:** messages missing a key field must be handled according to an explicit policy.
- **Reasonable distribution:** the key should not cause most messages to concentrate on a single partition.
- **Consistency across producers:** all producer instances must use the same normalization and key-generation rules.

Avoid putting the current timestamp, random numbers, or per-send generated IDs into a partition key when the goal is to group events of the same entity. Those values scatter related messages across multiple partitions.

## 4. PartitionSelectorStrategy: Selecting the Partition Index

`PartitionSelectorStrategy` takes the extracted key and the partition count. It must return a valid index in the range from `0` to `partitionCount - 1`.

With `OrderPartitionKey`, we can build a combined string of `tenantId` and `orderId` and then use hashing to distribute:

~~~java
import org.springframework.cloud.stream.binder.PartitionSelectorStrategy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PartitionSelectorConfiguration {

    @Bean
    PartitionSelectorStrategy tenantAwarePartitionSelector() {
        return (key, partitionCount) -> {
            if (partitionCount < 1) {
                throw new IllegalArgumentException(
                    "partitionCount must be greater than 0"
                );
            }

            if (!(key instanceof OrderPartitionKey orderKey)) {
                throw new IllegalArgumentException(
                    "Partition key must be OrderPartitionKey"
                );
            }

            String stableKey =
                orderKey.tenantId() + ":" + orderKey.orderId();

            return Math.floorMod(stableKey.hashCode(), partitionCount);
        };
    }
}
~~~

`Math.floorMod` ensures the result is always non-negative even when `hashCode()` returns a negative number. The selector must return a valid index; never return `partitionCount`, a negative number, or a value that depends on instance-local state.

### Default Selector vs. Custom Selector

If no custom selector is configured, Spring Cloud Stream typically uses a calculation based on the key's `hashCode` modulo `partitionCount`. A custom strategy lets you change the distribution behavior, but it must remain deterministic.

Example with `partitionCount = 6`:

| Key | Illustrative Index |
|---|---:|
| tenant-a:order-100 | 2 |
| tenant-a:order-101 | 3 |
| tenant-b:order-100 | 5 |
| tenant-a:order-100 (resent) | 2 |

This table only illustrates the principle; the actual index depends on the string's hash and `partitionCount`. What matters is that the same key, same algorithm, and same `partitionCount` yield the same index on every producer instance.

### Avoid Unstable Algorithms

Avoid partition selection based on:

- Random or round-robin selection when per-key ordering is needed.
- Current time or an in-memory counter local to a single instance.
- Object identity hash codes or memory-address-dependent details.
- Differing local configurations across producer instances.

If producer A chooses partition 1 for `order-100` while producer B chooses partition 4 for the same `order-100`, events for that order can be processed concurrently and out of order.

## 5. Registering and Selecting Beans in Spring Cloud Stream

Both strategies need to be registered as Spring beans. The default bean name is the `@Bean` method name—in our example:

- `orderPartitionKeyExtractor`
- `tenantAwarePartitionSelector`

Configure the output binding to use these two names:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderEvents-out-0:
          destination: orders
          producer:
            partitionCount: 6
            partitionKeyExtractorName: orderPartitionKeyExtractor
            partitionSelectorName: tenantAwarePartitionSelector
~~~

Meaning of the properties:

| Property | Role |
|---|---|
| `partitionCount` | Target number of partitions used by the producer to compute the index |
| `partitionKeyExtractorName` | Bean name implementing `PartitionKeyExtractorStrategy` |
| `partitionSelectorName` | Bean name implementing `PartitionSelectorStrategy` |

These properties sit under `producer` on the output binding. The binding name must match the actual output name of the `Supplier` or `Function` emitting the messages.

If the `ApplicationContext` contains only a single bean of each strategy type, the framework may auto-discover the matching bean. When multiple beans of the same type exist, specify the name explicitly to avoid selecting the wrong one. The name in configuration must match the registered bean name exactly.

### Two Mutually Exclusive Property Pairs

For the key extraction source, choose only one of the two:

- `partitionKeyExpression`
- `partitionKeyExtractorName`

For the partition selection algorithm, choose only one of the two:

- `partitionSelectorExpression`
- `partitionSelectorName`

Do not configure both options within the same pair simultaneously. If a custom extractor is used, do not add `partitionKeyExpression` to the same output binding. If a custom selector is used, do not add `partitionSelectorExpression`.

The legacy `partitionKeyExtractorClass` and `partitionSelectorClass` properties have been removed in current Spring Cloud Stream versions. Use bean names with `partitionKeyExtractorName` and `partitionSelectorName`; do not copy old class-based configuration from documentation of earlier versions.

## 6. End-to-End Producer and Consumer Configuration

Partitioning must be configured on both the sending and receiving sides. The producer determines the partition index; the consumer must be organized to read the corresponding partitions properly.

Example output binding:

~~~yaml
spring:
  cloud:
    function:
      definition: orderEvents
    stream:
      bindings:
        orderEvents-out-0:
          destination: orders
          producer:
            partitionCount: 6
            partitionKeyExtractorName: orderPartitionKeyExtractor
            partitionSelectorName: tenantAwarePartitionSelector
~~~

For the input binding, configure `partitioned` along with `instanceCount` and `instanceIndex` when the binder requires per-instance partition assignment:

~~~yaml
spring:
  cloud:
    function:
      definition: inventory
    stream:
      instanceCount: 3
      instanceIndex: 0
      bindings:
        inventory-in-0:
          destination: orders
          group: inventory
          consumer:
            partitioned: true
~~~

`instanceCount` is the total number of instances participating in partitioned processing. `instanceIndex` is each instance's unique index in the range `0` to `instanceCount - 1`. The example above represents the first instance in a three-instance cluster. When deploying three replicas, each replica must receive a distinct `instanceIndex`: `0`, `1`, and `2`; never assign the same value to all replicas.

How `instanceIndex` and `instanceCount` are used depends on the binder. With the Kafka binder, `autoRebalanceEnabled` defaults to `true`, so Kafka distributes partitions automatically within the consumer group; these two instance properties are usually unnecessary for default rebalancing. If `autoRebalanceEnabled` is disabled and partition assignment is delegated to the binder, configure both properties and ensure there are enough partitions for the number of instances. With RabbitMQ, the binder uses separate queues per partition, and the instance index participates in determining which queues an instance reads.

Do not hardcode a fixed `instanceIndex` in a shared configuration file for all replicas. Supply per-instance values from the deployment platform or application configuration management mechanism.

## 7. Impact of partitionCount

`partitionCount` is the number of partitions the selector uses to compute an index. The value must be greater than `1` to enable partitioning on an output binding.

The partition count affects:

- Maximum parallelism of a consumer group.
- Load distribution capability across instances.
- The number of queues or partitions the broker must manage.
- Key dispersion granularity.
- Processing order and application local state.

Do not increase `partitionCount` arbitrarily. With modulo hashing, when the partition count changes, many keys can shift to different partitions. Older messages for an entity may reside in old partitions while newer messages enter new partitions. If the system relies on per-key ordering or keeps per-partition state, this change requires a migration plan.

With Kafka, `partitionCount` in producer configuration is treated as a hint; the actual partition count of the topic may be larger, and the binder uses the greater of the configured count and the topic's partition count. Check the actual partition count on the topic rather than looking only at YAML values.

With RabbitMQ, the binder can provision a queue per partition. Increasing the partition count can change the number of queues and how queues are assigned to instances. Verify the actual topology before deploying.

With Pulsar, a topic can be a partitioned topic and the client has key-based routing mechanisms. How the binder maps Spring Cloud Stream's partitioning abstraction to a partitioned topic depends on the binder version and configuration. Check the capabilities of your specific binder and verify actual partitions on the broker.

## 8. Differences Between Kafka, RabbitMQ, and Pulsar

Spring Cloud Stream provides a common abstraction, but brokers have different partitioning models.

| Broker | Partitioning Structure | How Consumers Receive Data |
|---|---|---|
| Kafka | Topic consists of independently ordered partitions | Consumer group distributes partitions across members |
| RabbitMQ | Binder can simulate partitions using separate queues | Each instance receives queues/partitions per configuration |
| Pulsar | Topic can be split into multiple partitions | Subscription and consumer type determine distribution |

### Kafka

A Kafka partition is an ordered unit of storage. Messages in the same partition are read in ascending offset order. If a producer uses the same partition key for events of a single order, those events can land in the same partition and preserve write order within the partition.

Spring Cloud Stream's `PartitionKeyExtractorStrategy` and `PartitionSelectorStrategy` determine the target partition at the binder layer. Do not confuse the abstraction's internal partition key with the Kafka record key: how the binder maps these two concepts depends on the binder and its version. If an application needs a Kafka record key for compaction or other native logic, configure and test the record key separately as supported by the Kafka binder.

A consumer group distributes partitions across its members. At any given time, a partition is assigned to only one consumer member within the same group, though multiple independent groups can read the same topic.

### RabbitMQ

RabbitMQ does not organize queues by partitions like Kafka. The Rabbit binder can simulate partitioning by creating a queue per partition and routing messages to the corresponding queue. Configuring `instanceCount` and `instanceIndex` ensures each instance receives its assigned share of data.

Queue topology, queue names, and routing are managed by the binder. Verify the queue counts and bindings in the RabbitMQ Management UI after the application starts. Do not assume `partitionCount` in YAML corresponds to a native partition field inside an AMQP message.

### Pulsar

Pulsar supports partitioned topics and subscription types such as `Exclusive`, `Shared`, `Failover`, and `Key_Shared`. These mechanisms have their own distribution and ordering semantics. Pulsar's partition key can influence routing and ordering, whereas Spring Cloud Stream's `PartitionSelectorStrategy` returns a partition index under the shared abstraction.

When using the Pulsar binder, verify that your binder version supports the chosen partitioning mapping. If you need to guarantee that events with the same key are processed in order, check the partitioned topic, key/ordering key, and subscription type; do not rely solely on configuring the two strategies in the application.

## 9. Designing Keys to Preserve Entity Ordering

Partitioning is commonly used to send related messages to the same partition. For example:

- `OrderCreated`, `OrderPaid`, and `OrderShipped` events use `orderId`.
- Account update events use `accountId`.
- Sensor data uses `deviceId`.
- Multi-tenant events use a composite key of `tenantId` and `aggregateId`.

If only `tenantId` is used, all messages from one tenant may concentrate in a single partition and cause a hot partition. If only `orderId` is used when `orderId` is not unique across tenants, two tenants could accidentally share the same key. A composite key defines the exact entity scope.

A simple rule:

~~~java
String partitionKey = tenantId + ":" + aggregateId;
~~~

Standardize how keys are constructed. For example, `tenant-a:order-100` and `TENANT-A:ORDER-100` may be treated as two different keys if casing is inconsistent. If identifiers can contain whitespace, standardize whether trimming is applied across all producers.

### Preserving Ordering Is Not Exactly-Once Processing

Partitioning helps route related messages to the same partition; it does not by itself guarantee exactly-once processing. A consumer can still receive a message again due to retries, rebalances, or failures before acknowledgment. Handlers must be idempotent if business side effects must not repeat.

In addition, ordering is guaranteed within a partition according to broker semantics, not globally across all partitions. If events of the same entity are routed to a different partition due to an algorithm or `partitionCount` change, per-entity ordering is no longer preserved across that boundary.

## 10. Testing the Two Strategies

You should test the extractor and selector independently before testing against the broker.

### Testing the Extractor

Verify:

- Payloads of the right type are extracted into the expected key.
- Messages with the same `tenantId` and `orderId` produce the same key.
- Messages missing `tenantId` or `orderId` are rejected according to policy.
- Payloads of the wrong type are not cast or handled silently.
- Header keys are read accurately when using a header-based extractor.

### Testing the Selector

With a set of keys and `partitionCount`, verify:

- Results always lie within the range `0` to `partitionCount - 1`.
- The same key and same `partitionCount` always yield the same index.
- Changing `partitionCount` may change the index; this is behavior to manage deliberately.
- Distribution across a representative key set is not unexpectedly skewed.
- The selector rejects keys of the wrong type and invalid `partitionCount` values.

Example unit test for the selector:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class TenantAwarePartitionSelectorTest {

    private final PartitionSelectorStrategy selector =
        (key, count) -> {
            OrderPartitionKey orderKey = (OrderPartitionKey) key;
            String value = orderKey.tenantId() + ":" + orderKey.orderId();
            return Math.floorMod(value.hashCode(), count);
        };

    @Test
    void sameKeyAlwaysSelectsSamePartition() {
        OrderPartitionKey key =
            new OrderPartitionKey("tenant-a", "order-100");

        int first = selector.selectPartition(key, 6);
        int second = selector.selectPartition(key, 6);

        assertEquals(first, second);
        assertTrue(first >= 0 && first < 6);
    }
}
~~~

Unit tests do not prove the binder sends to the right partition on the broker. Broker integration tests are needed to verify the actual mapping.

## 11. End-to-End Testing with Multiple Instances

A realistic test should include:

1. Start the broker and create the destination with the expected partition count.
2. Start the producer with the custom extractor and selector.
3. Start at least two consumer instances in the same group.
4. Send multiple events for the same `orderId`.
5. Send events for multiple different `orderId` values and tenants.
6. Verify that events with the same key go to the same partition.
7. Verify that consumer instances receive partitions according to the binder mechanism.
8. Stop one consumer and observe rebalancing or queue assignment.
9. Restart the consumer and verify unprocessed messages are picked up according to broker policy.
10. Compare actual distribution against expected distribution.

With Kafka, inspect record partitions and offsets; with RabbitMQ, inspect per-partition queues and consumers; with Pulsar, inspect partitioned topics, subscriptions, and consumer assignments. Use administrative tools or clients capable of identifying the actual partition of each message.

Do not test solely by counting how many messages each consumer receives. Distribution will not necessarily be perfectly balanced in a small sample, especially when some keys occur more frequently. Verify the key-to-partition relationship first, then evaluate load across instances.

## 12. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Partitioning is not activated | `partitionCount` not set greater than 1 | Configure `partitionCount` on the output binding |
| Extractor bean not found | Bean name in configuration is incorrect | Match `partitionKeyExtractorName` to the `@Bean` name |
| Selector bean not found | Wrong bean name or bean not registered | Check `partitionSelectorName` and the `ApplicationContext` |
| Key is always null | Extractor reads wrong payload/header or message lacks field | Validate the message contract and test the extractor |
| Selector returns out-of-range partition | Algorithm does not normalize results | Use `Math.floorMod` and validate `partitionCount` |
| Events for same entity go to different partitions | Unstable key or producers use different algorithms | Normalize keys and align config across all producers |
| One partition receives too many messages | Low key cardinality or one entity emits excessive traffic | Re-evaluate the key and hot-key strategy |
| Consumers do not receive expected partitions | Wrong `instanceCount`/`index` or incompatible broker assignment | Check `consumer.partitioned`, `group`, and binder config |
| Changing `partitionCount` shifts key locations | Hash modulo depends on partition count | Plan migration and state handling |
| Kafka topic has different partition count from config | `partitionCount` is a hint; topic already existed with another count | Check actual topic and provisioning policy |
| RabbitMQ creates unexpected queues | Incorrect binder partitioning or instance index | Inspect queue topology and bindings on the broker |
| Pulsar does not preserve expected ordering | Unsuitable subscription type or key/partition mapping | Check binder version, topic, and subscription type |

When investigating issues, check in order: whether partitioning is enabled on the output binding, which key the extractor returns, which index the selector returns, what the actual `partitionCount` is, how the binder maps the index, and whether consumers are assigned the right partitions.

## 13. Hands-on Exercise: Partitioning Order Events

Build a producer emitting `OrderCreated` events and an inventory-updating consumer:

1. Declare `OrderCreated` with `eventId`, `tenantId`, `orderId`, `total`, and `occurredAt`.
2. Create `OrderPartitionKey` containing `tenantId` and `orderId`.
3. Implement `orderPartitionKeyExtractor` to read the payload and produce the key.
4. Implement `tenantAwarePartitionSelector` using `Math.floorMod` to return a valid index.
5. Register both strategies using `@Bean` with explicit names.
6. Configure output binding `orderEvents-out-0` with `partitionCount` equal to `6`, `partitionKeyExtractorName`, and `partitionSelectorName`.
7. Configure consumer `inventory` with destination `orders` and group `inventory`.
8. If the binder requires per-instance partition assignment, configure `partitioned`, `instanceCount`, and `instanceIndex` appropriately.
9. Send multiple events with the same `orderId` and verify they land in the same partition.
10. Send events across multiple tenants and orders to evaluate distribution.
11. Run multiple consumer instances and observe how the binder assigns partitions.
12. Change `partitionCount` in a test environment and record which keys shift partitions.
13. Write tests for null keys, wrong payload types, wrong selector key types, and invalid `partitionCount`.

Acceptance checklist:

| Item | Result to Verify |
|---|---|
| Extractor bean | Reads `Message` properly and returns a stable key |
| Selector bean | Returns an index within valid bounds |
| Bean name | Configuration matches bean names |
| Producer binding | Has `partitionCount` greater than 1 |
| Strategy selection | Does not declare both expression and custom name in the same pair |
| Consumer assignment | Instance index/count fits the binder |
| Same-key behavior | Same entity is sent to the same partition |
| Distribution | Load does not skew unexpectedly |
| Broker mapping | Actual partitions or queues match design |
| Change management | Plan exists when changing partition count or algorithm |

## Conclusion

`PartitionKeyExtractorStrategy` and `PartitionSelectorStrategy` allow splitting partitioning rules into two testable and reusable steps. The extractor obtains the key from a Spring `Message`; the selector converts the key into a partition index within the configured range. Spring Cloud Stream registers the strategies as beans and selects them via `partitionKeyExtractorName` and `partitionSelectorName` on the output binding.

Design stable keys around business entities, keep algorithms consistent across producers, and verify binder mappings on a real broker. Partitioning helps preserve ordering within a partition and distribute load, but does not by itself guarantee exactly-once processing or global ordering. Every change to `partitionCount`, algorithms, or consumer assignment must be tested and rolled out with a clear plan.

## References

- [Spring Cloud Stream – Partitioning](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-partitioning.html)
- [Spring Cloud Stream – Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)

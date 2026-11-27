# Distinguishing Stream Partition Keys from Kafka Record Keys

In Spring Cloud Stream and Kafka, the term "key" can refer to two different concepts. A **Spring Cloud Stream partition key** is the value the binder uses to compute the target partition according to the framework's partitioning configuration. A **Kafka record key** is the actual key field of a Kafka record, stored alongside the value and used by the Kafka producer when selecting a partition natively.

These two values can both come from `customerId`, but they are not automatically the same thing. A message can use a partition key to select a partition without carrying a Kafka record key; conversely, a message with a Kafka record key and no binder partitioning enabled lets Kafka select the partition itself. Understanding this boundary helps preserve per-key ordering, support log compaction, and avoid wrong assumptions when switching binders or changing partitioning algorithms.

## 1. Two Types of Keys Solve Different Problems

### Spring Cloud Stream Partition Key

Spring Cloud Stream provides a generic partitioning mechanism for output bindings. A producer can declare `partitionKeyExpression` to extract a value from the message. The framework uses that value along with `partitionCount` and the partition selector to compute the target partition index.

For example, with order events, an application wants all events for the same customer to land in the same partition. It can extract `customerId` from the payload or a header:

```yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
          producer:
            partition-key-expression: payload.customerId
            partition-count: 12
```

When binder partitioning is enabled, Spring Cloud Stream computes a partition index between `0` and `partitionCount - 1`. By default, the framework uses a calculation based on `key.hashCode() % partitionCount`; this can be customized with `partitionSelectorExpression` or a bean implementing `PartitionSelectorStrategy`.

The partition key here is the input to the partition selection algorithm. It is not necessarily written as the Kafka record key. This is a Spring Cloud Stream abstraction designed to support a shared partitioning model across binders, including middleware that lacks Kafka-style native partitions.

### Kafka Record Key

A Kafka record has three primary components: topic, key, and value, along with metadata such as partition, offset, and timestamp. The record key is actual data stored inside the record. By default, a Kafka producer uses the serialized key to pick a partition when the application does not specify a partition explicitly; records with the same key typically route to the same partition according to the configured partitioner.

In the Spring Cloud Stream Kafka binder, you can set the Kafka record key via the `KafkaHeaders.KEY` header:

```java
Message<OrderPlaced> message = MessageBuilder
    .withPayload(event)
    .setHeader(KafkaHeaders.KEY, event.customerId())
    .build();
```

The Kafka binder uses this header as the Kafka record's key. If neither a record key nor an explicit partition is provided, Kafka uses the producer's default partitioner to select a partition. The record key also matters for consumers, key-based processing, and log compaction when the topic is configured with an appropriate cleanup policy.

The Kafka record key is a Kafka-specific concept. When switching to RabbitMQ or Pulsar, you cannot assume the `KafkaHeaders.KEY` header carries the same meaning or is used by another binder.

## 2. Quick Comparison Table

| Criterion | Spring Cloud Stream Partition Key | Kafka Record Key |
|---|---|---|
| Which layer? | Spring Cloud Stream partitioning abstraction | Kafka record model |
| Used for what? | Computing the partition index via a partition selector | Stored as the record's key and participates in native partition selection |
| Common configuration | `partition-key-expression`, `partition-count` | `KafkaHeaders.KEY` or Kafka binder `message-key-expression` |
| Stored as the Kafka record key? | Not automatically | Yes |
| Scope of use | Applicable across multiple binders, depending on binder support | Meaningful only for Kafka |
| Default algorithm | Spring Cloud Stream hashes the key against partition count | Kafka producer runs its native partitioner on the serialized key |
| Impact on log compaction | Not directly | The record key is essential for compaction |
| When unconfigured | Binder partitioning is not enabled | Kafka picks a partition; if keyless, the partitioner handles keyless records |

Do not name a custom header `partitionKey` and assume Kafka will store that header as the record key. To give a record a key, set `KafkaHeaders.KEY` or configure the Kafka binder's `messageKeyExpression`.

## 3. Case A: Using Only the Spring Cloud Stream Partition Key

Suppose an application emits order events and needs to keep events for the same customer on the same partition. It builds a message with a dedicated header for the partition key:

```java
@Bean
Supplier<Message<OrderPlaced>> publishOrder() {
    return () -> {
        OrderPlaced event = nextOrderEvent();

        return MessageBuilder
            .withPayload(event)
            .setHeader("partitionKey", event.customerId())
            .build();
    };
}
```

Output binding configuration:

```yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
          producer:
            partition-key-expression: headers['partitionKey']
            partition-count: 12
```

The framework reads the `partitionKey` header, computes the partition index, and the binder sends the record to that partition. In this example, the `partitionKey` header determines the write location. It does not automatically become the Kafka record key.

With the Kafka binder, if no Kafka record key is supplied, the record can still be written to the binder-selected partition, yet the record's key may be `null`. In that case:

- Events with the same `partitionKey` can be routed by the binder to the same partition per the configured algorithm and partition count.
- Consumers read the record from that partition.
- The application lacks a corresponding Kafka record key to use directly for log compaction or downstream processing based on record keys.

This is an important distinction: selecting the right partition does not mean the record itself has a key.

## 4. Case B: Using Only the Kafka Record Key and Native Partitioning

If deploying exclusively on Kafka, you can often let Kafka select the partition using the record key. Omit `partition-key-expression`; instead, set `KafkaHeaders.KEY`:

```java
@Bean
Supplier<Message<OrderPlaced>> publishOrder() {
    return () -> {
        OrderPlaced event = nextOrderEvent();

        return MessageBuilder
            .withPayload(event)
            .setHeader(KafkaHeaders.KEY, event.customerId())
            .build();
    };
}
```

The Kafka binder sends `customerId` as the record key. The Kafka producer partitioner picks a partition based on the serialized key and the topic's current partition count. This configuration uses Kafka's native partitioning.

You can use the Kafka binder's `messageKeyExpression` property instead of the default key header if you want to pull the key from another header or expression:

```yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              message-key-expression: headers['kafkaKey']
```

When using this approach, the message must carry the `kafkaKey` header with an appropriate value. If you already set `KafkaHeaders.KEY` per binder convention, `messageKeyExpression` is usually unnecessary. Constant names can vary across Spring Kafka generations; use the constant specified in the documentation for your dependency version.

With Kafka native partitioning:

- The Kafka record key is stored inside the record.
- The Kafka producer selects the partition according to its configured partitioner.
- Records with the same key typically enter the same partition when the partition count and algorithm do not change.
- Consumer groups receive partitions via Kafka's assignment mechanism; no separate binder partitioning configuration is needed merely for Kafka to use the record key.

## 5. Case C: Using Both Keys

Sometimes both behaviors are needed simultaneously:

1. Spring Cloud Stream determines the exact partition index using the application's shared algorithm.
2. The Kafka record still carries the business key for consumers and log compaction.

In that case, set both the partition key header and the Kafka record key:

```java
@Bean
Supplier<Message<OrderPlaced>> publishOrder() {
    return () -> {
        OrderPlaced event = nextOrderEvent();
        String customerId = event.customerId();

        return MessageBuilder
            .withPayload(event)
            .setHeader("partitionKey", customerId)
            .setHeader(KafkaHeaders.KEY, customerId)
            .build();
    };
}
```

Binder partitioning configuration:

```yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
          producer:
            partition-key-expression: headers['partitionKey']
            partition-count: 12
```

In this case:

- Spring Cloud Stream uses `partitionKey` to compute the partition index.
- The Kafka binder sends the record to the partition specified by the binder partitioning result.
- `KafkaHeaders.KEY` supplies the actual key of the Kafka record.

When the partition is specified explicitly, Kafka does not need to pick a partition using the record key for that record. The record key is still stored and available to consumers or log compaction. If the two values differ, the record will still be written to the partition chosen by the partition key while storing a different value in the record key. Only do that when there is a clear reason; normally use the same business key to avoid confusion.

## 6. Why Can the Same Value Produce Different Partitions?

Suppose both modes use the string `customer-42` and the topic has 12 partitions.

With Spring Cloud Stream binder partitioning, the default calculation relies on `key.hashCode() % partitionCount`. With Kafka native partitioning, the Kafka producer runs Kafka's partitioner on the serialized key. The two algorithms are not guaranteed to match. Therefore, the same key string can be written to different partitions when an application switches between the two modes.

This matters especially when:

- Two different producers write to the same topic, with one using binder partitioning and the other using Kafka native partitioning.
- An application migrates from Spring Cloud Stream binder partitioning to Kafka Streams or `KafkaTemplate`.
- A system uses multiple producers written in Java, Python, or other languages.
- The application must guarantee that events for the same aggregate are processed in a consistent order.

If multiple producers must route the same key to the same partition, standardize the partitioning mechanism: either use Kafka native partitioning with matching key types, serializers, and partitioners, or explicitly configure a shared algorithm. Do not merely align the key string and assume the partition will match.

## 7. Partition Count and Impact on Ordering

A partition key is only meaningful relative to the partition selection algorithm and the partition count. When the partition count changes, modulo calculations or native partitioners can route keys to different partitions.

For example, a key may go to partition 2 when a topic has 6 partitions, yet move to a different partition when the topic expands to 12 partitions. Older records remain in the old partition; newer records may land in the new partition. Consequently, per-key ordering across the partition-expansion boundary is no longer guaranteed as a single sequence on the same partition.

Before increasing the partition count, evaluate:

- Ordering requirements by customer, order, or aggregate ID.
- Whether consumers can handle data for the same aggregate arriving from multiple partitions.
- Transition plans or acceptance of an ordering boundary.
- Compatibility across the partitioning algorithms of all producers.

In Kafka, ordering is guaranteed only within a single partition. Consistently routing the same key to the same partition is a standard way to preserve per-entity ordering, though it does not establish global ordering across all partitions.

## 8. Partition Keys and Record Keys in Other Binders

Spring Cloud Stream provides a partitioning abstraction so applications can express message distribution without full coupling to a single broker. `partitionKeyExpression` can be used with Kafka, RabbitMQ, or other binders if the binder supports partitioning.

Kafka's record key, by contrast, is tied to `ProducerRecord` and Kafka's partitioner. The `KafkaHeaders.KEY` header and the Kafka binder's `messageKeyExpression` property are not generic settings for RabbitMQ or Pulsar.

| Platform | Stream Partitioning Abstraction | Broker Native Key |
|---|---|---|
| Kafka | Binder can compute partition index from `partitionKeyExpression`; Kafka also has native partitioning | Kafka record key |
| RabbitMQ | Binder can map partitions to queues or corresponding structures per binder | No Kafka-style record key; exchanges/routing keys and queue bindings handle routing |
| Pulsar | Binder can map partitioning depending on supported features | Pulsar message key, used for routing/ordering per Pulsar configuration |

When writing multi-broker applications, use a generic header name like `partitionKey` to express partitioning intent at the application layer. Adapters or binder-specific configuration are responsible for mapping it to broker capabilities. Avoid coupling business services directly to `KafkaHeaders.KEY` if those services must run across multiple brokers.

## 9. Inspecting Partitions and Record Keys on the Consumer

To verify behavior, a Kafka consumer can read the received partition metadata:

```java
@Bean
Consumer<Message<OrderPlaced>> inspectOrder() {
    return message -> {
        OrderPlaced event = message.getPayload();

        Integer partition = message.getHeaders()
            .get(KafkaHeaders.RECEIVED_PARTITION, Integer.class);

        log.info(
            "Order {} for customer {} arrived on partition {}",
            event.orderId(),
            event.customerId(),
            partition
        );
    };
}
```

The `KafkaHeaders.RECEIVED_PARTITION` header indicates which partition the record was read from. This is metadata received from the Kafka binder, not Spring Cloud Stream's original partition key. To inspect the record key, read the key using the header/API supported by your Spring Kafka binder version, or use a Kafka consumer client in an integration test.

A useful testing strategy:

1. Unit test the partition key expression or extractor bean, verifying that messages for the same customer produce the same key value.
2. Test that the output binding configuration has the expected `partition-key-expression` and `partition-count`.
3. Run integration tests against real Kafka, emitting multiple records with the same key and reading back partition metadata.
4. Inspect the Kafka record key separately; do not infer the record key from the partition index.
5. Test a second producer using Kafka native partitioning to verify differences if the system mixes producer styles.

The Spring Cloud Stream Test Binder can test functions and bindings in memory, but it does not accurately simulate Kafka's native partitioner. To verify actual record keys and partitions, run integration tests against Kafka or an equivalent environment.

## 10. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Setting only the `partitionKey` header and expecting a Kafka record key | Record may land in the right partition, yet its key stays null | Also set `KafkaHeaders.KEY` or `messageKeyExpression` |
| Setting only `KafkaHeaders.KEY` while expecting Spring binder's partition selector to run | Kafka picks the partition itself; Stream's partition selector algorithm is bypassed | Configure `partition-key-expression` and `partition-count` if binder partitioning is required |
| Using `partitionCount` without checking the topic's actual partition count | Binder may not provision enough partitions or config mismatches | Manage topics and verify partition counts before deployment |
| Using different algorithms across producers | The same key can land in different partitions | Standardize partitioners, serializers, and configuration |
| Increasing partitions without evaluating ordering | Events for the same aggregate may be written to another partition after the change | Plan partition changes and test ordering |
| Using Kafka-specific headers in multi-broker services | Business code becomes coupled to Kafka | Use generic metadata at the application layer and map in adapters |

## 11. Selection Checklist

- Decide whether the goal is selecting partitions, storing a record key, or both.
- If Spring Cloud Stream binder partitioning is needed, configure `partition-key-expression` or `partition-key-extractor-name` along with `partition-count`.
- If Kafka native partitioning is needed, omit the binder partition expression and set the Kafka record key via `KafkaHeaders.KEY` or `message-key-expression`.
- If both are needed, configure each value explicitly and keep them aligned when representing the same aggregate/customer.
- Do not assume Spring Cloud Stream's hash algorithm matches Kafka's producer partitioner.
- Keep the partition count and algorithm consistent across all producers.
- Evaluate the impact of increasing partitions on per-key ordering.
- Verify partition metadata and record keys with Kafka integration tests.
- Keep business code independent of Kafka-specific headers when multi-binder support is needed.

## 12. References

- [Spring Cloud Stream Reference — Partitioning](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-partitioning.html), section on output binding configuration and partition selectors.
- [Spring Cloud Stream Kafka Binder — Partitioning with the Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/partitions.html), section distinguishing binder partitioning from Kafka native partitioning and `KafkaHeaders.KEY`.
- [Spring Cloud Stream Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html), section on producer properties `partitionKeyExpression`, `partitionCount`, and partition selectors.

Spring Cloud Stream's partition key determines how the framework computes the target partition; the Kafka record key is the actual key stored in the record that participates in Kafka's native partitioning mechanism. When portability across brokers is needed, use Stream's partitioning abstraction. When Kafka-specific features such as record keys and log compaction are required, configure the Kafka record key explicitly. If using both, clearly specify which value determines the partition and which value is stored in the record so producers, consumers, and operations share the same understanding.

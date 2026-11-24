# Sending to a Specific Partition

A Kafka producer normally lets the partitioner choose the partition based on the key or the default distribution policy. In some situations, an application needs to send a record to **a specific partition** to follow a defined routing rule, isolate a data stream, or remain compatible with an existing system's partitioning scheme. Spring Kafka supports this via `KafkaTemplate.send(...)` overloads and the `ProducerRecord` object.

In the `SPRING_KAFKA_MESSAGING` module, the producer sends events with `KafkaTemplate` and the consumer reads events with `@KafkaListener`. Specifying a partition is a producer-side decision; once written, the record still follows Kafka's storage, offset, and consumer group rules.

## 1. What is a partition and what does specifying a partition mean?

A topic is divided into multiple partitions. Each partition is an independently ordered log with its own offset sequence. When a producer sends a record, Kafka must determine which partition the record will be written to.

For example, topic `orders` has four partitions:

```text
orders
├── partition 0: offset 0, 1, 2, ...
├── partition 1: offset 0, 1, 2, ...
├── partition 2: offset 0, 1, 2, ...
└── partition 3: offset 0, 1, 2, ...
```

If the application specifies partition `2`, the record is sent to `orders-2`. Partition indices start at `0`, so a topic with four partitions has valid indices `0`, `1`, `2`, and `3`.

When no partition is specified, the producer can use the key and partitioner to choose. When a partition is specified explicitly, that partition takes precedence and the producer no longer uses the key to pick the partition. The key is still stored in the record for consumers and log compaction, but it no longer decides where that record is written.

| Send mode | Who selects the partition? | Role of the key |
|---|---|---|
| With key, no partition specified | Producer partitioner | Usually used for stable key-based routing |
| Without key and without partition specified | Default partitioner, may use sticky partitioning | No key for entity-based routing |
| Explicit partition specified | Application chooses the partition | Still stored in the record, but not used to pick the partition |

Specifying a partition does not create additional partitions and does not change the topic configuration. The topic must already have that partition before the producer sends the record.

## 2. Sending to a partition with `KafkaTemplate`

Spring Kafka provides an overload that takes topic, partition, key, and value:

```java
kafkaTemplate.send(topic, partition, key, value);
```

Example of a producer sending an order event to a provided partition:

```java
import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
            int partition,
            OrderCreatedEvent event) {

        if (partition < 0) {
            throw new IllegalArgumentException(
                    "Partition must be zero or greater"
            );
        }

        return kafkaTemplate.send(
                "orders",
                partition,
                event.orderId(),
                event
        );
    }
}
```

In this example:

- `"orders"` is the topic name.
- `partition` is the chosen partition index, starting from `0`.
- `event.orderId()` is still stored as the record's key.
- `event` is the payload converted into bytes by the serializer.

Checking `partition >= 0` only rejects negative indices. To be sure the partition exists, the application must check topic metadata or rely on controlled provisioning configuration. If sending to a non-existent partition, the broker may return an error such as `UNKNOWN_TOPIC_OR_PARTITION`; the producer does not create new partitions automatically.

In modern Spring Kafka versions (3.x), `KafkaTemplate.send(...)` returns `CompletableFuture<SendResult<K, V>>`. Older versions may use `ListenableFuture`; check the API of the dependency version in your project.

## 3. Creating `ProducerRecord` for full metadata control

When you also need to specify a timestamp or headers, create a `ProducerRecord` explicitly and send it with `KafkaTemplate`:

```java
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.internals.RecordHeader;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderRecordPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderRecordPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(int partition, OrderCreatedEvent event) {
        List<Header> headers = List.of(
                new RecordHeader(
                        "event-type",
                        "OrderCreated".getBytes(StandardCharsets.UTF_8)
                )
        );

        ProducerRecord<String, OrderCreatedEvent> record =
                new ProducerRecord<>(
                        "orders",
                        partition,
                        event.occurredAt().toEpochMilli(),
                        event.orderId(),
                        event,
                        headers
                );

        kafkaTemplate.send(record);
    }
}
```

The full constructor here accepts topic, partition, timestamp, key, value, and headers. The timestamp is passed in milliseconds since the Unix epoch. If you do not need a custom timestamp or headers, the `KafkaTemplate.send(...)` overload is more concise.

`ProducerRecord` only describes the record to be sent. The send outcome is still asynchronous and can fail due to network, broker, authorization, metadata, or serialization errors. In real applications, return the future to the caller or register a callback to observe the result rather than ignoring errors.

## 4. Verifying the partition before sending

The application needs to know whether the specified partition exists in the topic. You can read metadata with `KafkaTemplate.partitionsFor(topic)`:

```java
import java.util.List;

import org.apache.kafka.common.PartitionInfo;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class TopicPartitionValidator {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public TopicPartitionValidator(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void validate(String topic, int requestedPartition) {
        if (requestedPartition < 0) {
            throw new IllegalArgumentException("Negative partition index");
        }

        List<PartitionInfo> partitions = kafkaTemplate.partitionsFor(topic);
        boolean exists = partitions.stream()
                .anyMatch(info -> info.partition() == requestedPartition);

        if (!exists) {
            throw new IllegalArgumentException(
                    "Partition " + requestedPartition
                            + " does not exist in topic " + topic
            );
        }
    }
}
```

`partitionsFor(...)` fetches metadata from Kafka and can incur latency or connection failures. Do not call this method for every record in a high-throughput flow. Typically, verify topic/partition at application startup, when loading routing configuration, or on an administrative schedule; then use the validated configuration.

Pre-verification also does not completely eliminate send-time errors: the topic can change or a broker can fail after the check. The producer still needs to handle send failures.

## 5. Choosing a partition by business rules

There are three common ways to decide the partition:

1. **Fixed configuration:** the application sends one type of record to a configured partition, such as a legacy integration flow requiring partition `0`.
2. **Routing table:** the application looks up a centrally managed mapping such as `region -> partition` or `tenant -> partition`.
3. **Calculation from a routing key:** the application applies a deterministic algorithm so the same entity always yields the same partition.

Example of computing the partition by `accountId` with a known partition count:

```java
public final class AccountPartitionRouter {

    private final int partitionCount;

    public AccountPartitionRouter(int partitionCount) {
        if (partitionCount <= 0) {
            throw new IllegalArgumentException(
                    "Partition count must be positive"
            );
        }
        this.partitionCount = partitionCount;
    }

    public int partitionFor(String accountId) {
        return Math.floorMod(accountId.hashCode(), partitionCount);
    }
}
```

`Math.floorMod(...)` guarantees a non-negative result, even when `hashCode()` returns a negative number. With the same `accountId` and the same `partitionCount`, the algorithm above yields the same partition in a Java application.

This is only an example of self-managed routing. It is not the same hash algorithm used by Kafka's default partitioner. If the producer can let Kafka select the partition from the key, prefer the default mechanism to avoid maintaining a routing algorithm yourself. Only compute partitions manually when there is a clear business requirement or compatibility with an existing mapping is needed.

If multiple languages or services compute partitions together, publish the exact hash algorithm, key normalization rules, and negative-number handling. Do not let each service implement a different algorithm.

## 6. Impact on key, ordering, and consumer groups

### 6.1. Key still exists but does not determine the partition

Suppose a record has key `order-1001`, yet the producer specifies partition `3`. Kafka stores the record with that key in partition `3`, even if the default partitioner would have chosen a different partition for the same key.

This gives the application control over where records are written, but it also means the producer must ensure events that need to stay together are routed consistently. If one event for `order-1001` is sent to partition `1` and the next event to partition `3`, Kafka cannot guarantee ordering across the two partitions.

### 6.2. Ordering is only guaranteed within a single partition

Kafka maintains record order within each partition by offset. If all events for the same aggregate are always sent to the same partition and the producer sends them in the desired order, consumers can read the sequence of records in that partition's offset order.

Kafka does not guarantee global ordering across partitions. Identical or increasing timestamps also do not replace offset ordering. If multiple producers write to the same partition concurrently, the order is determined by the order in which the broker appends records, not necessarily the business chronological order observed independently by the producers.

### 6.3. How do consumer groups receive partitions?

Specifying a partition on the producer does not force a specific consumer to receive the record. Kafka consumer groups still use the assignment mechanism to distribute partitions among consumer members. Within the same group, a partition is assigned to at most one member at a time.

Example of a topic with four partitions and a consumer group with two consumers:

```text
Topic orders                 Consumer group orders-service
partition 0 ────────────────> consumer A
partition 1 ────────────────> consumer A
partition 2 ────────────────> consumer B
partition 3 ────────────────> consumer B
```

A record sent to partition `3` will be read by whichever consumer currently owns partition `3` in the group. It will not necessarily go to consumer B forever; assignments can change during a rebalance.

Do not confuse producer-side partition specification with `@TopicPartition` or `TopicPartitionOffset` on the consumer side. One decides where to write the record; the other decides which partitions the consumer subscribes to or is assigned.

## 7. When should you and shouldn't you specify a partition?

| Situation | Recommendation | Reason |
|---|---|---|
| Need to preserve a standardized partition mapping from a legacy system | Can specify partition | Compatible with existing routing rules |
| Have tenant/region partitioning rules requiring explicit control | Can use a routing table or router | Enables load coordination according to business needs |
| Just need events with the same `orderId` to go to the same partition | Usually just use `orderId` as the key | The Kafka partitioner already handles key-based routing |
| Want to increase throughput by sending all records to one partition | Do not do this | A single partition becomes a bottleneck and limits consumer parallelism |
| Want to force a specific consumer to process a record | Do not use partition as a consumer identifier | Consumer group assignment is managed by Kafka and can change |
| Want global ordering across all topics | Cannot be solved by specifying a partition | Ordering only has meaning within each partition of a topic |

Specifying a partition is a routing control tool, not a default speedup technique. If there is no clear requirement, let the Kafka partitioner choose based on the key.

## 8. Handling send results and partition errors

Sending a record is an asynchronous operation. Applications need to distinguish pre-send errors (such as a negative partition index), metadata/partition errors, serialization errors, and broker errors returned after sending.

Example of observing send results:

```java
import java.util.concurrent.CompletableFuture;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class AuditedOrderPublisher {

    private static final Logger log =
            LoggerFactory.getLogger(AuditedOrderPublisher.class);

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public AuditedOrderPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
            int partition,
            OrderCreatedEvent event) {

        CompletableFuture<SendResult<String, OrderCreatedEvent>> future =
                kafkaTemplate.send("orders", partition, event.orderId(), event);

        return future.whenComplete((result, exception) -> {
            if (exception != null) {
                log.error(
                        "Failed to publish order {} to partition {}",
                        event.orderId(),
                        partition,
                        exception
                );
                return;
            }

            var metadata = result.getRecordMetadata();
            log.info(
                    "Published order {} to topic={} partition={} offset={}",
                    event.orderId(),
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset()
            );
        });
    }
}
```

The returned record metadata shows the actual partition and offset written by the broker. This is useful data for cross-checking during debugging. Do not log only the requested partition; inspect the partition in `RecordMetadata` to confirm the actual result.

Do not retry infinitely on configuration errors such as a non-existent partition or wrong topic name. For transient errors like connection loss, apply retries/backoff aligned with producer configuration and business policy. If the send result fails, the caller must decide whether to report an error, retry, or record state for later handling.

## 9. Configuring and managing partitions per environment

Do not hardcode partition indices scattered across many classes. If you must specify partitions, put routing rules in configuration or a dedicated component:

```yaml
app:
  kafka:
    topics:
      orders: orders
    routing:
      orders:
        default-partition: 0
```

This example is only appropriate when the actual requirement is to always send to partition `0`. If the topic is created with different partition counts between local and production, verify configuration values before running. With key-based routing, the partition count configuration must stay synchronized with topic metadata and all producers participating in the same stream.

When increasing a topic's partition count, the `hash(key) % partitionCount` algorithm can map the same key to a new partition. If per-entity ordering is a strict requirement, you need a migration plan for the mapping, handling existing data, and avoiding the same entity being written to both old and new partitions simultaneously.

With a routing table, version the mapping and roll out changes synchronously across producers. If two instances use two different versions of the mapping, events for the same key could be sent to different partitions during deployment.

## 10. Testing a producer that sends to a specific partition

Tests should verify that the record is actually written to the requested partition, while also checking the key and payload.

Appropriate test levels:

- **Router unit test:** verify the same routing key yields consistent results, the partition is within the valid range, and negative hashes are handled properly.
- **Publisher unit test:** mock `KafkaTemplate`, verify the `send(topic, partition, key, value)` overload is called with the right arguments and the caller receives the future.
- **Integration test with Embedded Kafka or Testcontainers:** create a topic with a known partition count, send a record to a partition, then read metadata or consume to verify the actual partition.
- **Error tests:** try a negative partition, out-of-range partition, non-existent topic, or unavailable broker; verify the application handles errors according to policy.

Integration test examples should use a dedicated test topic and not rely on the broker's default partition count. When checking results, prefer `RecordMetadata.partition()` from the send result or `ConsumerRecord.partition()` rather than checking only that the payload was received.

## 11. Common mistakes

- **Confusing 1-based partition indices:** Kafka numbers from `0`; a four-partition topic uses indices `0` through `3`.
- **Specifying an out-of-range partition:** the producer sends to a non-existent partition and receives an error from the broker. Verify metadata or provisioning.
- **Thinking the key still picks the partition when a partition is passed:** the specified partition takes precedence; the key only remains record data.
- **Sending events for the same aggregate to different partitions:** ordering between them is not guaranteed. Maintain consistent routing.
- **Funneling all records into partition `0`:** causes a hot partition and limits parallel consumption.
- **Computing partitions against a changing partition count:** the same key can get remapped when the topic grows in partitions.
- **Confusing producer partition with consumer assignment:** the producer chooses where to write; the Kafka consumer group decides which consumer member reads the partition.
- **Ignoring the future returned by `send`:** the application fails to detect asynchronous send failures.
- **Validating the partition on every record:** repeated metadata calls increase overhead; validate on startup or when routing configuration changes.

## 12. Checklist before sending to a specific partition

- [ ] There is a clear business reason to specify a partition instead of using key-based partitioning.
- [ ] Partition index starts at `0` and is within the current topic's range.
- [ ] The topic has been provisioned with an appropriate partition count.
- [ ] Routing rules are consistent across producers and instances.
- [ ] Events that require per-entity ordering are sent to the same partition.
- [ ] Risk of hot partitions and load distribution has been evaluated.
- [ ] Impact of increasing partition count or changing routing mappings has been accounted for.
- [ ] The producer observes the send result and handles asynchronous errors.
- [ ] Integration tests verify the actual partition via metadata or consumer records.

When specifying a partition purposefully, the producer can control where records are written while keeping the key, value, timestamp, and headers as usual. Maintain a unified routing rule, validate partitions against topic metadata, and track send results to ensure the messaging flow retains the desired ordering and scalability.

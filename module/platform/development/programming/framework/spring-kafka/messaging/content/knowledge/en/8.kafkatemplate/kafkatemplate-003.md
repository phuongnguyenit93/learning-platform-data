# send to a Specific Topic and Key

`KafkaTemplate` is the standard data-sending API in Spring Kafka. When calling `send(topic, key, data)`, the application specifies the destination topic, the key used for routing, and the payload to send. The producer serializes the key/value and selects a partition based on the key if the application does not specify a concrete partition.

This is the right send pattern for most event streams: using the entity ID as the key so related records generally land in the same partition, allowing consumers to process changes in order within each partition. `send` operates asynchronously, so the application must track send outcomes and handle errors appropriately.

## 1. Sending records with KafkaTemplate

`KafkaTemplate<K, V>` is Spring Kafka's helper class for sending records. The two generic parameters describe the key and value types that the producer factory/serializers are configured to handle.

For example, an application sends order events to the `orders.events` topic:

```java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        Instant occurredAt,
        BigDecimal total
) {}
```

The publisher uses `KafkaTemplate<String, OrderCreatedEvent>`:

```java
import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private static final String TOPIC = "orders.events";

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
            OrderCreatedEvent event) {
        return kafkaTemplate.send(TOPIC, event.orderId(), event);
    }
}
```

In `send(TOPIC, event.orderId(), event)`:

- `TOPIC` is the target topic name.
- `event.orderId()` is the record key.
- `event` is the value/payload to be serialized.

KafkaTemplate builds the record and hands it off to the Kafka producer to send to the broker. The application does not need to instantiate `ProducerRecord` manually for simple cases requiring only topic, key, and value.

## 2. Choosing keys for record routing

The key identifies a group of related records. With the Kafka producer's default partitioner, the serialized key is used to compute the partition. Therefore, if all events for the same order use `orderId` as the key, they are generally routed to the same partition as long as the partition count, key serializer, and partitioning strategy remain unchanged.

Example:

| Event | Key | Purpose |
|---|---|---|
| `OrderCreated` for O100 | `O100` | Create order |
| `OrderPaid` for O100 | `O100` | Update payment |
| `OrderPacked` for O100 | `O100` | Update packing |
| `OrderCreated` for O200 | `O200` | Create another order |

Events for O100 share the same key and can be written to the same partition; O200 has a different key and may reside in another partition. Kafka preserves record order within each partition, so a consumer can process O100's changes in offset order while still processing O200 in parallel.

Choose keys based on the entity that needs serialization of updates:

- `orderId` for changes to an order.
- `accountId` for transactions that must be applied in order on an account.
- `deviceId` for the state sequence of a device.
- `customerId` for changes to a customer profile.

Do not default to using `eventId` as the key. `eventId` identifies a single event occurrence; the key usually needs to group multiple events belonging to the same entity. The two values can differ because they serve different purposes.

### Conditions for stable key mapping

Keys only keep related records in the same partition when producers follow consistent conventions. Keep in mind:

1. All producers must represent and serialize keys identically. For example, the string `O100` must be serialized consistently.
2. Use the same partitioning strategy. Custom partitioners may route differently from the default partitioner.
3. Do not change the partition count arbitrarily. Increasing partitions can change key-to-partition mapping; old and new records for the same key may end up in different partitions.
4. Keys do not enforce business ordering on their own. If multiple threads publish events for the same aggregate concurrently, append order depends on the order in which brokers receive the records. Applications must coordinate emission or use a sequence/version number to verify business order.

## 3. Common send overloads

KafkaTemplate has multiple overloads to send records with the required level of detail. Common forms:

| Call | Meaning |
|---|---|
| `send(topic, data)` | Sends a value to the topic without providing a key. |
| `send(topic, key, data)` | Sends a value with a key for the partitioner to route. |
| `send(topic, partition, key, data)` | Specifies partition, key, and value. |
| `send(topic, partition, timestamp, key, data)` | Specifies partition and timestamp along with key/value. |
| `send(ProducerRecord)` | Sends a pre-built record that may include headers and other fields. |

The most common case is `send(topic, key, data)`:

```java
kafkaTemplate.send("orders.events", event.orderId(), event);
```

When calling `send(topic, data)`, the key is `null`. The producer can still send the record, but you cannot rely on a key to keep events of the same entity in one partition.

### Specifying a partition only when truly necessary

You can specify a partition directly:

```java
int targetPartition = 2;

kafkaTemplate.send(
        "orders.events",
        targetPartition,
        event.orderId(),
        event
);
```

Partition indices are zero-based and must exist in the topic. When a partition is specified, the producer sends the record to that partition instead of letting the partitioner choose. This is useful when the application has custom partitioning rules, but requires care to avoid skew or splitting the same key across multiple partitions.

If you need to specify a timestamp:

```java
long eventTimestamp = event.occurredAt().toEpochMilli();

kafkaTemplate.send(
        "orders.events",
        null,             // Let the partitioner choose the partition.
        eventTimestamp,
        event.orderId(),
        event
);
```

Timestamps are measured in milliseconds from the Unix epoch. The timestamp seen by consumers also depends on the topic's `message.timestamp.type` (`CreateTime` or `LogAppendTime`). Timestamps do not replace offsets and do not establish global ordering across partitions.

## 4. Configuring serializers for key and value

Kafka stores data as bytes. `KafkaTemplate` requires a producer factory with key and value serializers matching the template's generic types.

Example Spring Boot configuration for a `String` key and JSON value:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
```

With this configuration:

- `StringSerializer` converts `orderId` into key bytes.
- `JsonSerializer` converts `OrderCreatedEvent` into JSON value bytes.

The consumer needs a matching deserializer or message converter to decode the value. Both sides must agree on the schema and how type headers/default types are handled. For other key/value types, choose matching serializers; for example, `LongSerializer` for a `Long` key or `StringSerializer` for a `String` value.

If serializer configuration is incompatible with the generic types or actual payload, serialization errors can happen in the producer before the record is ever sent to the broker. Verify both compile-time types and runtime serializer configuration.

## 5. Asynchronous sending and receiving results

`KafkaTemplate.send(...)` does not wait for the broker to finish writing before returning. In modern Spring Kafka, `send` methods return `CompletableFuture<SendResult<K, V>>`. The future completes when the producer receives a success or error result.

You can handle the result directly at the call site:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public void publish(OrderCreatedEvent event) {
    Logger log = LoggerFactory.getLogger(getClass());

    kafkaTemplate.send("orders.events", event.orderId(), event)
            .whenComplete((result, exception) -> {
                if (exception != null) {
                    // Record the error and route according to the retry/error handling policy.
                    log.error("Failed to send event orderId={}",
                            event.orderId(), exception);
                    return;
                }

                var metadata = result.getRecordMetadata();
                log.info("Sent orderId={} to topic={}, partition={}, offset={}",
                        event.orderId(),
                        metadata.topic(),
                        metadata.partition(),
                        metadata.offset());
            });
}
```

`SendResult` provides `RecordMetadata` showing the topic, partition, offset, and timestamp of the broker-acknowledged record. This information is useful for logging, metrics, and tracing. An offset is the record's position within a partition, not the business ID of the event.

Another option is returning the future to the caller so it can decide whether to wait, compose, or handle errors:

```java
public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
        OrderCreatedEvent event) {
    return kafkaTemplate.send("orders.events", event.orderId(), event);
}
```

Do not ignore the future if the business logic must be certain the send was acknowledged by the broker. A `send` call returning without throwing only means the producer accepted the send request; actual delivery may still fail due to serialization errors, timeouts, broker unavailability, or network issues.

## 6. Consumer receiving key and value

A consumer can accept `ConsumerRecord<K, V>` to access the key, value, and Kafka metadata:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    @KafkaListener(
            topics = "orders.events",
            groupId = "order-projection"
    )
    public void onOrderEvent(
            ConsumerRecord<String, OrderCreatedEvent> record) {

        String orderId = record.key();
        OrderCreatedEvent event = record.value();

        System.out.printf(
                "orderId=%s, partition=%d, offset=%d%n",
                orderId,
                record.partition(),
                record.offset()
        );

        // Update the projection based on the event.
    }
}
```

If a listener only accepts `OrderCreatedEvent`, Spring Kafka can convert the payload directly using the configured deserializer/converter. Use `ConsumerRecord` when you need the key, partition, offset, timestamp, or headers.

## 7. Pitfalls to avoid when sending with a key

### Using inconsistent keys

If producer A uses `orderId` while producer B uses `eventId`, events for the same order can go to different partitions. Define the key in the integration contract and use it consistently across all producers.

### Assuming a key guarantees absolute business order

A key only supports routing into the same partition. Kafka preserves the order in which records are appended to a partition, but it does not inherently know that `OrderCreated` must precede `OrderPaid`. If multiple producers emit concurrently, coordinate the emission source or add a sequence/version field for consumers to validate.

### Changing partition counts without assessing impact

Increasing partitions can alter key hash routing. For topics requiring per-aggregate ordering, plan a migration or use a pre-designed stable routing mechanism.

### Failing to handle asynchronous send errors

The producer can fail after the `send` method has already returned a future. Observe the future, log errors with context, and decide on retries or error handling per application policy. Retries must be designed to avoid duplicating side effects or breaking ordering.

## 8. Key takeaways

- `kafkaTemplate.send(topic, key, data)` sends a payload to a topic with an application-chosen key.
- After serialization, the key is used by the partitioner for routing; identical keys generally land in the same partition if partition count and strategy stay constant.
- Choose keys by aggregate such as `orderId`, `accountId`, or `deviceId` when entity state changes need ordering.
- `send(topic, data)` has no key; other overloads allow specifying partition or timestamp.
- Key/value serializers must match `KafkaTemplate`'s data types and the consumer-side deserializers.
- `send` is asynchronous; monitor `CompletableFuture<SendResult<K, V>>` for outcomes and broker metadata.
- Keys do not order events semantically on their own; producers must emit in the right order and consumers must handle side effects appropriately.

When sending an event with `KafkaTemplate`, choose the topic matching the contract, use a key representing the routing entity, configure compatible serializers, and track the asynchronous result. These four decisions form the foundation for a scalable producer flow that still preserves necessary ordering within each partition.

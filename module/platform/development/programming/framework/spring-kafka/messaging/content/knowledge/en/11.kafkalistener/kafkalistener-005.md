# Reading Message<?> in Listeners

In Spring Kafka, a `@KafkaListener` method can accept the deserialized payload directly, accept `ConsumerRecord<K, V>` to access the low-level Kafka API, or accept Spring Messaging's `Message<?>`. `Message<?>` wraps the payload together with headers describing the record such as topic, partition, offset, key, and timestamp. This lets the listener handle data and metadata in a single parameter using Spring's abstraction.

In the `SPRING_KAFKA_MESSAGING` module, consumers receive events from Kafka via `@KafkaListener`. When you need to inspect metadata for logging, tracing, or forwarding to an application use case, `Message<?>` is a useful option. Note that the `?` wildcard indicates the payload type is not explicitly declared at compile time; the actual runtime type is still determined by the deserializer or message converter.

## 1. What Is `Message<?>`?

`Message<T>` belongs to Spring Messaging (`org.springframework.messaging.Message`). A message has two main parts:

- `getPayload()`: the primary data received by the listener.
- `getHeaders()`: the metadata collection of type `MessageHeaders`.

`Message<?>` means the payload has some Java type, but the listener method does not declare that specific type. When reading `message.getPayload()`, the compiler treats the result as `Object`; the application must check the type before casting or processing.

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class OrderMessageListener {

    @KafkaListener(topics = "orders", groupId = "orders-service")
    public void listen(Message<?> message) {
        Object payload = message.getPayload();
        String payloadType = payload == null
                ? "null"
                : payload.getClass().getName();
        System.out.println("Payload type: " + payloadType);
        System.out.println("Payload: " + payload);
        System.out.println("Headers: " + message.getHeaders());
    }
}
```

Spring Kafka converts a `ConsumerRecord` into a Spring `Message` via the listener container's message converter. Therefore, `Message<?>` is not a raw byte record from the broker; its payload has already passed through the deserialization and/or conversion configured for the consumer.

## 2. Structure of a Spring `Message`

A message can be pictured as follows:

```text
Message<OrderCreatedEvent>
├── payload
│   └── OrderCreatedEvent(orderId=order-1001, ...)
└── headers (MessageHeaders)
    ├── kafka_receivedTopic      = "orders"
    ├── kafka_receivedPartition  = 2
    ├── kafka_offset              = 184
    ├── kafka_receivedTimestamp  = 1731741000000
    ├── kafka_receivedKey        = "order-1001"
    └── correlation-id           = ...
```

The header names shown above illustrate their meaning. In code, use `KafkaHeaders` constants rather than typing Kafka header string names directly. `MessageHeaders` may also contain standard Spring headers such as `id` and `timestamp`; these differ from the record's Kafka timestamp.

| Component | API | Purpose |
|---|---|---|
| Payload | `message.getPayload()` | Deserialized/converted event or data |
| Headers | `message.getHeaders()` | Spring and Kafka metadata mapped onto the message |
| Topic | `KafkaHeaders.RECEIVED_TOPIC` | Topic from which the record was received |
| Partition | `KafkaHeaders.RECEIVED_PARTITION` | Partition containing the record |
| Offset | `KafkaHeaders.OFFSET` | Offset of the record within the partition |
| Key | `KafkaHeaders.RECEIVED_KEY` | Key deserialized by the consumer |
| Timestamp | `KafkaHeaders.RECEIVED_TIMESTAMP` | Kafka timestamp received on the record |

`MessageHeaders` is a read-only header structure. A listener can read values from it, but should not treat this map as a place to mutate business state. If you need to build a new Spring `Message`, use `MessageBuilder` in the message-creation layer rather than mutating incoming headers directly.

## 3. Reading Kafka Metadata from `MessageHeaders`

Spring Kafka provides constants in `org.springframework.kafka.support.KafkaHeaders`. Example:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.stereotype.Component;

@Component
public class OrderMetadataListener {

    @KafkaListener(topics = "orders", groupId = "orders-observer")
    public void listen(Message<?> message) {
        MessageHeaders headers = message.getHeaders();

        String topic = headers.get(
                KafkaHeaders.RECEIVED_TOPIC, String.class);
        Integer partition = headers.get(
                KafkaHeaders.RECEIVED_PARTITION, Integer.class);
        Long offset = headers.get(KafkaHeaders.OFFSET, Long.class);
        Long timestamp = headers.get(
                KafkaHeaders.RECEIVED_TIMESTAMP, Long.class);
        Object key = headers.get(KafkaHeaders.RECEIVED_KEY);

        System.out.printf(
                "topic=%s partition=%s offset=%s timestamp=%s key=%s%n",
                topic, partition, offset, timestamp, key
        );

        Object payload = message.getPayload();
        // Forward payload to the next processing step.
    }
}
```

Metadata headers are useful for logging and comparing against consumer lag. An offset is meaningful only within a partition; do not use offset alone to uniquely identify a record across an entire topic. When uniquely identifying a record, combine topic, partition, and offset.

A header may be absent in certain contexts or have a different type depending on converter/header mapper configuration. Therefore, when metadata is optional, handle `null` values properly. Do not cast blindly without verifying the actual header type.

## 4. Reading Strongly Typed Payloads

If a listener always handles one event type, declare the concrete payload type so the compiler can assist with type checking:

```java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        BigDecimal total,
        Instant occurredAt
) {}
```

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class TypedOrderListener {

    @KafkaListener(topics = "orders", groupId = "orders-projection")
    public void listen(Message<OrderCreatedEvent> message) {
        OrderCreatedEvent event = message.getPayload();
        System.out.println("Order ID: " + event.orderId());
    }
}
```

`Message<OrderCreatedEvent>` still provides all the same headers as `Message<?>`, while giving the payload an explicit type. This generic type must match the data produced by the Kafka deserializer or message converter.

If a single listener needs to read multiple event types, it can accept `Message<?>` and branch based on the payload type or an agreed `event-type` header:

```java
@KafkaListener(topics = "domain-events", groupId = "domain-event-router")
public void listen(Message<?> message) {
    Object payload = message.getPayload();

    if (payload == null) {
        throw new IllegalArgumentException("Event payload must not be null");
    } else if (payload instanceof OrderCreatedEvent orderCreated) {
        handleOrderCreated(orderCreated);
    } else if (payload instanceof PaymentCapturedEvent paymentCaptured) {
        handlePaymentCaptured(paymentCaptured);
    } else {
        throw new IllegalArgumentException(
                "Unsupported event payload: " + payload.getClass().getName()
        );
    }
}
```

This example assumes the deserializer has already turned the payload into the corresponding Java types. If the payload is always a `String` or `byte[]`, parse/deserialize according to the schema before processing. Avoid relying solely on class names in headers if producer and consumer do not share a compatible schema contract.

## 5. Configuring Deserialization So `Message<?>` Receives the Right Payload

`Message<?>` does not decide whether a payload is JSON, `String`, or a byte array. The payload type depends on the Kafka `value.deserializer` and the `RecordMessageConverter` configured on the listener container factory.

Example consumer using `JsonDeserializer` with a fixed target type:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    consumer:
      group-id: orders-service
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.orders.OrderCreatedEvent
        spring.json.trusted.packages: com.example.orders
        spring.json.use.type.headers: false
```

In this example, `JsonDeserializer` produces a payload of type `OrderCreatedEvent`. When the listener accepts `Message<?>`, `getPayload()` returns the deserialized object; the compiler only sees `Object` because of the wildcard generic. If you want compile-time type checking, use `Message<OrderCreatedEvent>`.

For systems with multiple event types, define an explicit schema/type strategy: managed type headers, per-topic default types, converters with appropriate target types, or a schema registry. Do not expand `trusted.packages` indiscriminately; trust only the packages required by the serializer/deserializer setup in use.

If using `StringDeserializer`, the payload is typically a `String`; if using `ByteArrayDeserializer`, it is typically a `byte[]`. You can configure a `RecordMessageConverter` to convert payloads into application types, but ensure the converter has enough target-type information. The wildcard `Message<?>` gives the compiler no concrete payload type.

## 6. Reading Custom Headers from Producers

A producer can add headers to a `ProducerRecord`:

```java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.internals.RecordHeader;

ProducerRecord<String, OrderCreatedEvent> record =
        new ProducerRecord<>("orders", event.orderId(), event);

record.headers().add(new RecordHeader(
        "correlation-id",
        correlationId.getBytes(StandardCharsets.UTF_8)
));

kafkaTemplate.send(record);
```

Consumer reading the custom header from `MessageHeaders`:

```java
import java.nio.charset.StandardCharsets;

byte[] rawCorrelationId = message.getHeaders().get(
        "correlation-id", byte[].class);

String correlationId = rawCorrelationId == null
        ? null
        : new String(rawCorrelationId, StandardCharsets.UTF_8);
```

The Java type observed by the consumer for custom headers depends on `KafkaHeaderMapper` and its mapping configuration. The example above assumes the header is preserved as `byte[]`. If the mapper converts it to `String` or another type, read using the actual mapped type and agree on encoding between producer and consumer. When tighter mapping control is needed, configure a dedicated mapper on the listener container factory.

Do not place core business data in custom headers. Headers are suited for correlation IDs, trace context, event types, or small metadata; the payload should still carry the event content to be processed.

## 7. Using `@Header` When Only a Few Values Are Needed

If a listener needs only a few metadata fields, it does not necessarily have to accept the full `Message<?>`. You can declare the payload and headers as separate parameters:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.stereotype.Component;

@Component
public class OrderHeaderListener {

    @KafkaListener(topics = "orders", groupId = "orders-audit")
    public void listen(
            @Payload OrderCreatedEvent event,
            @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
            @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
            @Header(KafkaHeaders.OFFSET) long offset) {

        System.out.printf(
                "Received order=%s from %s-%d offset=%d%n",
                event.orderId(), topic, partition, offset
        );
    }
}
```

`Message<?>` works well when handling payload and multiple headers together as a single unit. `@Payload` and `@Header` work well when the method signature should clearly display the required values. Both rely on Spring Kafka's message conversion and argument resolution mechanisms.

## 8. `Message<?>` or `ConsumerRecord<K, V>`?

These two parameter types address different needs:

| Criterion | `Message<?>` | `ConsumerRecord<K, V>` |
|---|---|---|
| Abstraction | Spring Messaging | Kafka Java client |
| Payload | `getPayload()` returns `Object` with wildcard | `value()` returns `V` |
| Metadata | Via `MessageHeaders` and `KafkaHeaders` | Via methods `topic()`, `partition()`, `offset()`, `timestamp()`, etc. |
| Custom headers | Mapped through header mapper | Read directly from `record.headers()` |
| Best suited for | Integration with Spring Messaging, header mapping, and handler methods | Full access to Kafka records/metadata or low-level Kafka APIs |
| Dependency | Spring Messaging and Spring Kafka converters | Kafka client API |

If an application use case only needs the event and a few selected metadata values, pass those values into a simple command/application input. Avoid leaking `Message<?>` or `ConsumerRecord` into the domain layer when business logic does not need Kafka details.

## 9. Notes on Acknowledgment and Error Handling

`Message<?>` can contain an acknowledgment header if the listener container is configured for manual acknowledgment. For example, with `AckMode.MANUAL`, Spring Kafka can put the `Acknowledgment` object into the `KafkaHeaders.ACKNOWLEDGMENT` header.

```java
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;

@KafkaListener(topics = "orders", groupId = "orders-manual-ack")
public void listen(Message<?> message) {
    Acknowledgment acknowledgment = message.getHeaders().get(
            KafkaHeaders.ACKNOWLEDGMENT,
            Acknowledgment.class
    );

    process(message.getPayload());

    if (acknowledgment != null) {
        acknowledgment.acknowledge();
    }
}
```

Use this pattern only when the listener container is configured with an appropriate acknowledgment mode. Under automatic ack modes, the acknowledgment header may not exist. In practice, acknowledge only after processing succeeds per your chosen semantics; if processing fails, let the error handler/retry policy decide how to proceed. Never acknowledge early before business work finishes.

If the listener method throws an exception, Spring Kafka handles it according to the container's error handler, retry, and recovery configuration. Receiving `Message<?>` does not alter offset commit semantics. Headers only supply data to the listener; they do not enable manual ack or retries on their own.

## 10. Testing Listeners That Accept `Message<?>`

Test both payload and metadata:

- **Unit test:** construct a Spring `Message` using `MessageBuilder.withPayload(...)` with mock headers, then test processing logic decoupled from Kafka.
- **Listener test:** send a record to a test topic, verify the payload is deserialized, and check that the listener reads the right topic, partition, offset, key, or custom headers.
- **Serialization test:** verify the producer serializer, consumer deserializer, and header mapper produce the expected data types.
- **Error test:** send a schema-invalid payload or omit optional headers, and confirm the listener does not fail with unexpected cast errors.
- **Acknowledgment test:** if using manual ack, verify `acknowledge()` is called only after successful processing.

With Embedded Kafka or Testcontainers, create dedicated test topics and use a separate consumer group per test. When asserting offsets/partitions, read values from `KafkaHeaders` or `ConsumerRecord` rather than assuming records are always written to partition `0`.

## 11. Common Pitfalls

- **Assuming `Message<?>` holds raw bytes:** the payload has already passed through the deserializer and/or message converter. Check consumer configuration before casting.
- **Casting payloads without checking:** the wildcard gives the payload a compile-time type of `Object`; use `instanceof` or `Message<T>` when the type is fixed.
- **Confusing `MessageHeaders.TIMESTAMP` with the Kafka timestamp:** use `KafkaHeaders.RECEIVED_TIMESTAMP` when you need the Kafka record's timestamp.
- **Using arbitrary string header names for standard metadata:** prefer `KafkaHeaders` constants to avoid typos.
- **Assuming custom headers are always `String`:** headers may be `byte[]` or another type depending on the mapper; align encoding and mapping.
- **Treating `MessageHeaders` as a mutable map:** incoming headers are read-only; create a new message if transformation is needed.
- **Passing `Message<?>` into the domain layer:** the domain should receive required business data without depending on messaging abstractions unnecessarily.
- **Thinking `Message<?>` enables manual ack by itself:** acknowledgment mode must be configured on the listener container.
- **Using `Message<?>` when the full Kafka API is needed:** if you need client-level record/header manipulation, accepting `ConsumerRecord<K, V>` is more appropriate.

## 12. Checklist for Reading `Message<?>`

- [ ] Confirmed the payload type produced by the deserializer or message converter.
- [ ] Used `Message<T>` when the payload type is fixed; used `Message<?>` when flexible handling is needed.
- [ ] Read Kafka metadata using `KafkaHeaders` constants.
- [ ] Handled cases where a header is absent or has an unexpected type.
- [ ] Distinguished the Kafka timestamp from the Spring message timestamp.
- [ ] Standardized mapping and encoding for custom headers.
- [ ] Passed only necessary payload/metadata into the application use case.
- [ ] Avoided mutating `MessageHeaders` directly.
- [ ] Used the acknowledgment header only when the container is configured for manual ack.
- [ ] Added integration tests verifying real payloads and metadata.

Accepting `Message<?>` lets listeners read payloads alongside metadata within a consistent Spring abstraction. Once you understand how the payload type is determined by the deserializer/converter, use `KafkaHeaders` properly, and pass only necessary information into the application layer, consumers stay observable and maintainable while keeping a clean boundary with the Kafka client.

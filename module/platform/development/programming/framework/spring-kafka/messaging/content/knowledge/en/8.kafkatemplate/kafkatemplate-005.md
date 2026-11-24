# Sending Message<?> via KafkaTemplate

## Lesson Objectives

In the **KafkaTemplate** chapter, this lesson guides you through sending a Spring Messaging `Message<?>` using KafkaTemplate. This approach lets you bundle a payload together with metadata in headers, after which Spring Kafka converts the message into a Kafka ProducerRecord for the producer to send to the broker.

**SPRING_KAFKA_MESSAGING** focuses on building applications that send and receive Kafka events using Spring Kafka, KafkaTemplate, and @KafkaListener; it also helps learners understand topics, partitions, offsets, consumer groups, serialization, retries, dead-letter handling, transactions, exactly-once semantics, concurrency, and testing. Within that flow, KafkaTemplate is the Spring-side producer API; the `send(Message<?>)` method is useful when an event needs to carry a key, topic, partition, timestamp, or metadata for tracing and integration.

After this lesson, learners will be able to:

- Distinguish Spring `Message<?>` from Kafka `ProducerRecord` and business payloads.
- Build a `Message` using `MessageBuilder` and set the required Kafka headers.
- Send messages using `KafkaTemplate.send(Message<?>)`.
- Understand how Spring Kafka maps topic, key, partition, timestamp, and custom headers.
- Configure serializers compatible with the payload type.
- Handle asynchronous send results and send failures.
- Test both the payload and metadata of a Kafka record.

## 1. What is Message<?>?

Spring Messaging defines the `Message<T>` abstraction to package two parts:

- **Payload:** the primary data the application wants to transmit.
- **Headers:** metadata accompanying the message, such as content type, correlation ID, source information, or attributes controlling delivery.

Example of a message representing an order event:

~~~text
Payload:
{
  "orderId": "order-10001",
  "customerId": "customer-20001",
  "total": 1250000
}

Headers:
topic       = commerce.order.created
key         = order-10001
trace-id    = trace-7f31
contentType = application/json
~~~

The payload describes the business event. Headers carry routing information or metadata that producers, consumers, and observability systems can use.

`Message<?>` is a Spring abstraction, not a Kafka record. When sending a message via KafkaTemplate, Spring Kafka converts it into a `ProducerRecord<K, V>`, and then the Kafka producer serializes the key/value and sends the record to the broker.

~~~mermaid
flowchart LR
    A["Message<?>"] --> B["MessagingMessageConverter"]
    B --> C["ProducerRecord<K, V>"]
    C --> D["Kafka Serializer"]
    D --> E["Kafka Broker"]
    A1["Payload"] --> B
    A2["Headers"] --> B
~~~

Therefore, distinguish three layers:

| Component | Role |
|---|---|
| Spring `Message<?>` | Packages payload and headers inside a Spring application |
| Kafka `ProducerRecord<K, V>` | Represents a Kafka record containing topic, partition, key, timestamp, headers, and value |
| Kafka serialized record | Key/value data converted to bytes by serializers for transmission over the Kafka protocol |

## 2. When should you use send(Message<?>)?

KafkaTemplate provides several overloads to send records. Overloads taking topic, key, and value are usually suitable when you only need to pass basic data:

~~~java
kafkaTemplate.send(topic, key, value);
~~~

Use `send(Message<?>)` when you want to encapsulate sending information inside a Spring `Message` object:

- You want to put the topic and key into headers.
- You want to pass a correlation ID or trace ID alongside the event.
- You want to attach metadata following Spring Messaging conventions.
- You want to pass a message through multiple processing layers without passing the payload and each metadata parameter separately.
- You want to leverage `MessageBuilder` to construct an immutable message after building.

If you are only sending a simple payload without metadata, the `send(topic, key, value)` overload is usually more concise. When headers or Spring Messaging integration are needed, `send(Message<?>)` keeps data and metadata together in a single object.

## 3. Important Kafka headers

Spring Kafka provides constants in `KafkaHeaders` to map Spring Message headers to the corresponding fields of a Kafka `ProducerRecord`.

| Header | Typical value type | Meaning |
|---|---|---|
| `KafkaHeaders.TOPIC` | `String` | Target topic name |
| `KafkaHeaders.KEY` | Type `K` of KafkaTemplate | Record key |
| `KafkaHeaders.PARTITION` | `Integer` | Explicitly specified target partition |
| `KafkaHeaders.TIMESTAMP` | `Long` | Record timestamp |
| Custom header | `String`, `byte[]`, or mapper-supported type | Metadata such as trace ID, source, or correlation ID |

With `send(Message<?>)`, provide `KafkaHeaders.TOPIC` to identify the target topic unless the application has configured a default topic and uses the corresponding default-send mechanism.

Routing headers serve distinct roles:

- **TOPIC** determines the data stream.
- **KEY** participates in determining the partition via the partitioner and helps group related records.
- **PARTITION** specifies a partition directly when the application has an explicit reason.
- **TIMESTAMP** supplies the record timestamp; how the broker uses it depends on timestamp type configuration.

Do not confuse outbound headers with headers Spring Kafka creates to describe received records, such as `RECEIVED_TOPIC` or `RECEIVED_PARTITION`. `RECEIVED_*` headers are normally populated on the consumer side.

## 4. Creating a Message with MessageBuilder

Spring provides `MessageBuilder` to create messages using a fluent API. The payload is passed to `withPayload`; metadata is added with `setHeader`.

Suppose the application has an event:

~~~java
public record OrderCreated(
    String orderId,
    String customerId,
    long total
) {
}
~~~

Centralized topic declarations:

~~~java
public final class KafkaTopics {

    private KafkaTopics() {
    }

    public static final String ORDER_CREATED =
        "commerce.order.created";
}
~~~

Creating the message:

~~~java
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public Message<OrderCreated> buildMessage(
        OrderCreated event,
        String traceId) {

    return MessageBuilder.withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, KafkaTopics.ORDER_CREATED)
        .setHeader(KafkaHeaders.KEY, event.orderId())
        .setHeader("trace-id", traceId)
        .build();
}
~~~

In this example:

- The payload is `OrderCreated`.
- `TOPIC` selects the `commerce.order.created` topic.
- `KEY` uses `orderId` so events for the same order are generally routed to the same partition with the default partitioner.
- `trace-id` helps correlate logs and traces across services.

`MessageBuilder` produces a `Message` whose headers are managed according to Spring's abstraction. After calling `build()`, do not try to mutate headers of the created message; if metadata needs to change, create a new message from the builder.

### 4.1. Adding partition and timestamp

If business logic or partitioning design requires sending to a specific partition, you can set `KafkaHeaders.PARTITION`:

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setHeader(KafkaHeaders.TOPIC, KafkaTopics.ORDER_CREATED)
    .setHeader(KafkaHeaders.KEY, event.orderId())
    .setHeader(KafkaHeaders.PARTITION, 2)
    .build();
~~~

When a partition is specified, the producer sends the record to that partition instead of letting the partitioner choose. Do this only when the application genuinely needs partition control; hard-coding partitions can cause load skew or break key distribution strategies when partition counts change.

You can supply a timestamp:

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setHeader(KafkaHeaders.TOPIC, KafkaTopics.ORDER_CREATED)
    .setHeader(KafkaHeaders.TIMESTAMP, System.currentTimeMillis())
    .build();
~~~

The record timestamp does not replace a business timestamp inside the payload. If you need to distinguish when the business event occurred from when the producer sent it, model both explicitly in the event or metadata.

## 5. Sending Message<?> with KafkaTemplate

Suppose the producer is configured for `String` keys and `OrderCreated` values:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event,
            String traceId) {

        Message<OrderCreated> message = MessageBuilder
            .withPayload(event)
            .setHeader(KafkaHeaders.TOPIC, KafkaTopics.ORDER_CREATED)
            .setHeader(KafkaHeaders.KEY, event.orderId())
            .setHeader("trace-id", traceId)
            .build();

        return kafkaTemplate.send(message);
    }
}
~~~

The `send(Message<?>)` method accepts a Spring `Message` and converts it into a Kafka record. Applications do not have to construct `ProducerRecord` manually in typical cases.

In Spring Kafka 3.x, `send` methods return `CompletableFuture<SendResult<K, V>>`. Older Spring Kafka versions may use `ListenableFuture`; check the API of the version you are using when writing callbacks.

### 5.1. What happens when calling send?

The send flow can be described as follows:

~~~mermaid
sequenceDiagram
    participant A as Application
    participant T as KafkaTemplate
    participant M as Message Converter
    participant P as Kafka Producer
    participant B as Kafka Broker

    A->>T: send(Message<?>)
    T->>M: Convert Message to ProducerRecord
    M-->>T: ProducerRecord<K,V>
    T->>P: send(record)
    P->>P: Serialize key and value
    P->>B: Produce request
    B-->>P: Produce response
    P-->>T: Send result / exception
    T-->>A: CompletableFuture
~~~

Key steps:

1. The application creates a `Message` with payload and headers.
2. KafkaTemplate invokes the message converter to create a `ProducerRecord`.
3. The converter reads Kafka headers to determine topic, key, partition, and timestamp; remaining metadata is mapped into Kafka record headers according to the mapper configuration.
4. The Kafka producer serializes key/value into bytes.
5. The producer sends the record to the broker.
6. The send result is completed through the future.

If the topic header is missing and no appropriate default topic is configured, record conversion will fail. If the payload is incompatible with the serializer, sending can also fail.

## 6. Distinguishing Message Converter and Serializer

These are two components with different responsibilities.

### 6.1. Message Converter

The message converter turns a Spring `Message` into a Kafka `ProducerRecord`. It handles reading headers and creating a record with topic, key, partition, timestamp, headers, and payload.

With KafkaTemplate, this mechanism lets the application send `Message<?>` without manually mapping every header onto a `ProducerRecord`.

### 6.2. Serializer

The serializer converts key and value into bytes so the Kafka producer can transmit them over the network.

Example configuration:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
~~~

This configuration means:

- The key is a `String` and is serialized by `StringSerializer`.
- The `OrderCreated` payload is serialized to JSON by `JsonSerializer`.

If `StringSerializer` is used for the value, the payload needs to be a `String`. If the payload is `byte[]`, a matching serializer is required. Simply creating a `Message<?>` does not automatically turn an arbitrary object into JSON; the producer serializer must still match the value type.

### 6.3. Content-Type does not replace the serializer

You can add a `Content-Type` header to describe the format:

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setHeader(KafkaHeaders.TOPIC, KafkaTopics.ORDER_CREATED)
    .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
    .build();
~~~

`Content-Type` is useful metadata for integration systems and compatible converters. It does not replace the Kafka producer's key/value serializer configuration. Producer and consumer must still agree on the actual wire format.

## 7. Custom headers and passing metadata

Beyond Kafka routing headers, applications can attach custom metadata:

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setHeader(KafkaHeaders.TOPIC, KafkaTopics.ORDER_CREATED)
    .setHeader(KafkaHeaders.KEY, event.orderId())
    .setHeader("trace-id", traceId)
    .setHeader("event-source", "order-service")
    .setHeader("event-type", "OrderCreated")
    .build();
~~~

Common purposes include:

- `trace-id`: links logs and distributed traces.
- `event-source`: identifies the application emitting the event.
- `event-type`: helps classify events when required by the contract.
- `correlation-id`: ties a request to its outcome or related events.
- `schema-version`: identifies the data contract if the system defines this metadata.

Kafka record headers are a collection of key/byte-value pairs. Spring Kafka uses `KafkaHeaderMapper` to map between Spring Message headers and Kafka headers. The default mapper supports common types according to its rules; for custom types, configure the mapper and explicit serialize/deserialize conventions.

Do not place large payloads inside headers. Headers are meant for small metadata; business data belongs in the payload. Avoid putting tokens, passwords, or sensitive data into headers because metadata frequently appears in logs, tracing, and administrative tools.

## 8. Handling asynchronous send results

`KafkaTemplate.send(Message<?>)` is an asynchronous operation. It returns `CompletableFuture<SendResult<K, V>>` in Spring Kafka 3.x.

You can process the outcome using `whenComplete`:

~~~java
public void publish(OrderCreated event, String traceId) {
    Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, KafkaTopics.ORDER_CREATED)
        .setHeader(KafkaHeaders.KEY, event.orderId())
        .setHeader("trace-id", traceId)
        .build();

    kafkaTemplate.send(message)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                log.error(
                    "Cannot publish order event, orderId={}",
                    event.orderId(),
                    exception
                );
                return;
            }

            RecordMetadata metadata =
                result.getRecordMetadata();

            log.info(
                "Published order event, topic={}, partition={}, offset={}",
                metadata.topic(),
                metadata.partition(),
                metadata.offset()
            );
        });
}
~~~

When sending succeeds, `SendResult` provides the sent `ProducerRecord` and the `RecordMetadata` returned by the broker. Metadata is typically used to log the record's topic, partition, and offset.

There is no need to block the calling thread with `get()` just to wait for the result if processing can continue asynchronously. Blocking web or business threads for long durations can reduce application throughput.

### 8.1. Distinguishing synchronous and asynchronous errors

Some errors can arise immediately during the `send` call, such as argument validation failures, message conversion errors, or producer errors occurring before the future is returned. Other errors are reported via the future when the send operation finishes unsuccessfully.

If full handling is required, combine `try/catch` around `send` with the future's callback:

~~~java
try {
    kafkaTemplate.send(message)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                handleAsyncFailure(exception);
            } else {
                handleSuccess(result);
            }
        });
} catch (RuntimeException exception) {
    handleImmediateFailure(exception);
}
~~~

Do not swallow exceptions or merely log them and treat the event as emitted. If business logic requires guaranteed event emission, have a proper retry strategy, delivery state tracking, or the Outbox Pattern.

## 9. Factors affecting the send result

Send success from the producer's perspective depends on Kafka producer configuration and broker responses.

Key properties to watch:

| Property | Role |
|---|---|
| `acks` | Acknowledgement level the producer requires from brokers |
| `retries` | Number of times the producer retries recoverable request errors |
| `enable.idempotence` | Enables producer idempotence to curb duplicates from producer retries within Kafka's guarantees |
| `delivery.timeout.ms` | Upper bound on total wait time for send success or failure |
| `request.timeout.ms` | Time limit waiting for a request response |
| `max.block.ms` | Maximum time producer APIs can block waiting for metadata or buffer space |

Example producer configuration:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      retries: 10
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
~~~

Concrete values should be chosen based on Kafka client version, system load, and reliability requirements. Producer idempotence helps avoid certain duplicate records from producer retries, but does not guarantee end-to-end business execution occurs exactly once.

A future completing successfully means publishing was acknowledged according to producer and broker settings. It does not mean a consumer has received, processed, or committed the offset for the event.

## 10. Key, partition, and ordering when sending Message<?>

The key is typically placed in `KafkaHeaders.KEY`:

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setHeader(KafkaHeaders.TOPIC, KafkaTopics.ORDER_CREATED)
    .setHeader(KafkaHeaders.KEY, event.orderId())
    .build();
~~~

When no partition is specified, the producer's partitioner decides the partition. With the default partitioner and a non-null key, records with the same key are usually routed to the same partition as long as the partition count and partitioner configuration stay unchanged.

This helps when ordering events of the same order within a partition. Kafka guarantees ordering within a partition; there is no global order across multiple partitions.

If `KafkaHeaders.PARTITION` is set, the application specifies the partition directly. In that case, verify the partition exists and evaluate the impact on load distribution, ordering, and scalability.

Do not use a timestamp or trace ID as the key just because they are handy. Choose the key according to the business entity that needs ordering or data locality.

## 11. Common errors when sending Message<?>

| Symptom | Possible cause | What to check |
|---|---|---|
| Cannot determine topic | Missing `KafkaHeaders.TOPIC` and no default topic | Check message headers and default topic |
| Producer sends wrong key | Wrong header name or incompatible key type | Use `KafkaHeaders.KEY` and verify serializer |
| Record lands in unexpected partition | Null key, different partitioner than expected, or explicit partition set | Check key, partitioner, and `KafkaHeaders.PARTITION` |
| Payload cannot be serialized | Value serializer incompatible with payload | Check value type and producer configuration |
| Custom header does not reach consumer | Header mapper does not map the data type or header name | Check `KafkaHeaderMapper` and record headers |
| Future completes with error | Broker, timeout, serialization, or producer failure | Inspect exception, producer metrics, and broker logs |
| Send succeeds but consumer does not process | Consumer group, subscription, offset, or listener issue | Check consumer group, lag, and listener |
| Event processed repeatedly | Producer retry, consumer redelivery, or non-idempotent business logic | Distinguish producer idempotence from consumer idempotency |

A frequent mistake is naming headers with arbitrary strings instead of using `KafkaHeaders.TOPIC` or `KafkaHeaders.KEY`. When that happens, the converter may fail to recognize routing metadata, leaving the record without a topic or key.

## 12. Testing send(Message<?>) with Kafka

Integration tests should verify both the payload and metadata of the record.

Testing steps:

1. Start a test Kafka broker with EmbeddedKafka or Testcontainers.
2. Create a KafkaTemplate with compatible serializers.
3. Build a `Message<OrderCreated>` using `MessageBuilder`.
4. Send the message and await future completion in the test.
5. Read the record from the topic using a test consumer.
6. Assert payload, key, partition, and custom headers.

Example illustrating verification of the received record:

~~~java
ConsumerRecord<String, OrderCreated> record =
    KafkaTestUtils.getSingleRecord(
        consumer,
        KafkaTopics.ORDER_CREATED
    );

assertThat(record.key()).isEqualTo("order-10001");
assertThat(record.value().orderId()).isEqualTo("order-10001");

Header traceHeader = record.headers().lastHeader("trace-id");
assertThat(traceHeader).isNotNull();
assertThat(new String(traceHeader.value(), StandardCharsets.UTF_8))
    .isEqualTo("trace-7f31");
~~~

How custom headers are read depends on the configured mapper and header serialization. For `byte[]` headers, verify the byte contents using the exact encoding the producer used.

Besides happy-path tests, cover cases such as:

- Missing topic header.
- Payload incompatible with serializer.
- Broker unavailable.
- Custom header with a type unsupported by the mapper.
- Key and partition mapped correctly.
- Future completing with an error routed to the proper handling mechanism.

Do not only assert that the publish method throws no exception. Confirm the record was actually written to the topic and critical metadata was preserved.

## 13. Complete end-to-end walkthrough

Suppose the Order service emits `OrderCreated` for Billing to process.

### Step 1: Declare producer configuration

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
~~~

### Step 2: Define the event

~~~java
public record OrderCreated(
    String orderId,
    String customerId,
    long total
) {
}
~~~

### Step 3: Build a Message with headers

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setHeader(KafkaHeaders.TOPIC, KafkaTopics.ORDER_CREATED)
    .setHeader(KafkaHeaders.KEY, event.orderId())
    .setHeader("trace-id", traceId)
    .setHeader("event-source", "order-service")
    .build();
~~~

### Step 4: Send using KafkaTemplate

~~~java
CompletableFuture<SendResult<String, OrderCreated>> future =
    kafkaTemplate.send(message);
~~~

### Step 5: Observe the result

~~~java
future.whenComplete((result, exception) -> {
    if (exception != null) {
        log.error("Publish failed for {}", event.orderId(), exception);
        return;
    }

    RecordMetadata metadata = result.getRecordMetadata();
    log.info(
        "Published to {}-{} at offset {}",
        metadata.topic(),
        metadata.partition(),
        metadata.offset()
    );
});
~~~

### Step 6: Verify on the consumer

The Billing consumer reads the `commerce.order.created` topic, inspects the payload and headers needed for tracing or business processing. If the consumer requires idempotent handling, the event should include a stable event ID in the payload or metadata agreed upon in the contract.

Complete flow:

~~~mermaid
flowchart TD
    A["Order Service creates OrderCreated"] --> B["MessageBuilder.withPayload"]
    B --> C["Add TOPIC, KEY, and trace-id"]
    C --> D["KafkaTemplate.send(Message<?>)"]
    D --> E["Message Converter"]
    E --> F["ProducerRecord"]
    F --> G["Serializer"]
    G --> H["Kafka Broker"]
    H --> I["Billing Consumer"]
    D --> J["CompletableFuture"]
    J --> K["Record success or failure"]
~~~

## 14. Checklist before using send(Message<?>)

- [ ] Does the payload type match `KafkaTemplate<K, V>`?
- [ ] Does the message have `KafkaHeaders.TOPIC` or an appropriate default topic?
- [ ] Is `KafkaHeaders.KEY` chosen according to the partitioning strategy?
- [ ] Is `KafkaHeaders.PARTITION` set only when partition targeting is genuinely needed?
- [ ] Does the timestamp have clear semantics and use milliseconds?
- [ ] Are custom headers small and of types supported by the mapper?
- [ ] Are secrets or sensitive data kept out of headers?
- [ ] Are key/value serializers compatible with actual data?
- [ ] Is the future observed to handle results and exceptions?
- [ ] Do `acks`, `retries`, and idempotence policies meet requirements?
- [ ] Can the consumer read the payload and headers properly?
- [ ] Do tests verify topic, key, payload, and record metadata?

## Conclusion

`KafkaTemplate.send(Message<?>)` enables a Spring application to send a `Message` containing payload and headers. Spring Kafka converts the `Message` into a `ProducerRecord`, maps Kafka headers such as `TOPIC`, `KEY`, `PARTITION`, and `TIMESTAMP`, and then the Kafka producer serializes key/value and sends the record to the broker.

This approach fits well when events need metadata for routing, tracing, or Spring Messaging integration. To use it properly, distinguish the message converter from the serializer, choose keys and partitions intentionally, monitor `CompletableFuture`, and test both payloads and headers. Producer success is defined by the configured acknowledgement; consumers still require their own processing, offset management, and idempotency mechanisms to ensure a reliable messaging flow.

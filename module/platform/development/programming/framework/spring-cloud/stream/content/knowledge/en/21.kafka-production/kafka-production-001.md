# Choosing the Record Key with messageKeyExpression or a Kafka Header

A Kafka record has two main data parts: **key** and **value**. The value typically carries the business payload; the key helps Kafka route the record to a partition and supports entity-based data organization. For an order stream, choosing `orderId` as the key helps events for the same order generally go to the same partition. For topics using log compaction, the key also identifies the group of records for which Kafka retains the latest value.

The Spring Cloud Stream Kafka Binder lets you set the record key in two common ways: configuring **messageKeyExpression** to extract the key from the outgoing message, or setting the Kafka key header directly using **KafkaHeaders.KEY**. Both approaches produce a key for the Kafka record. It is important to distinguish them from regular custom headers and from Spring Cloud Stream's general partitioning mechanism.

## 1. What is a Kafka record key?

A Kafka record can be visualized as follows:

~~~text
ProducerRecord
  topic: orders.events
  partition: (chosen by the producer or explicitly specified)
  key: "ORD-1001"
  value: {"orderId":"ORD-1001","status":"CONFIRMED"}
  headers:
    eventType: OrderConfirmed
    correlationId: corr-81
~~~

The key and value are serialized separately using the key serializer and value serializer. The key is a dedicated field of `ProducerRecord`, not part of the JSON payload and not a regular Kafka header.

When the producer does not specify a concrete partition, the Kafka partitioner uses the key to select a partition. With a non-null key, the default partitioner typically hashes the key to choose a partition in the topic. With a null key, the Kafka producer may use a different distribution strategy, such as sticky partitioning; therefore, you should not assume messages without a key will be distributed evenly by hash.

Records with the same key are typically sent to the same partition as long as the partition count and partitioning strategy do not change. Kafka preserves append order within each partition, which is the foundation for maintaining event ordering for the same entity. There is no global ordering across partitions.

## 2. Choosing keys by business entity

The key should represent the entity by which the application wants to group or preserve ordering:

| Event type | Suitable key | Benefit |
|---|---|---|
| Order state changes | orderId | Events for a single order are grouped into the same partition |
| Account transactions | accountId | Updates for an account can be processed sequentially |
| Customer profile changes | customerId | Consumers can easily build per-customer projections |
| Inventory updates | sku | Changes for the same product are grouped under the same key |

For example, if an order sequentially emits `OrderCreated`, `OrderPaid`, and `OrderShipped`, using the same `orderId` as the key ensures the records are written to the same partition. Consumers can read them in the order the broker wrote them to that partition.

Do not choose a random key for each message if the goal is to group events by entity. Do not use a timestamp instead of a business key when entity stability is required: timestamps can collide, suffer from clock skew, or fail to reflect the exact order in which the broker receives records.

Keys must have a value and be normalized identically across producers. If one producer uses `customer-10` and another uses `CUSTOMER-10`, they may be routed to different partitions even though they refer to the same customer.

## 3. Setting the key with messageKeyExpression

`messageKeyExpression` is a Kafka Binder-specific property. The binder evaluates a SpEL expression against the outgoing message and uses the result as the Kafka record key.

For example, suppose the payload has the type:

~~~java
record OrderEvent(
        String orderId,
        String customerId,
        String eventType,
        long sequence) {}
~~~

Declare the binding and the expression to extract the key from the payload:

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.events
          content-type: application/json
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              messageKeyExpression: payload.orderId
              configuration:
                key.serializer: org.apache.kafka.common.serialization.StringSerializer
~~~

In this example:

- `publishOrder-out-0` is the output binding used by the `publishOrder` function.
- `destination` maps the binding to the `orders.events` topic.
- `messageKeyExpression: payload.orderId` extracts `orderId` from the outgoing message payload.
- `key.serializer` tells Kafka how to encode the `String` key into bytes.

Example event-publishing function:

~~~java
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderProducerConfiguration {

    @Bean
    Supplier<OrderEvent> publishOrder() {
        return () -> new OrderEvent(
                "ORD-1001",
                "CUS-01",
                "OrderCreated",
                1);
    }
}
~~~

When the supplier emits a message, the Kafka Binder evaluates the expression against the payload and produces a record with key `ORD-1001`. The key does not need to be repeated in the value if consumers can obtain the identifier from the key; however, keeping the identifier in the payload is also often useful so the data remains self-describing when transferred to other systems.

`messageKeyExpression` is unset by default. If there is no expression and the message does not carry a Kafka key header, the record may be sent with a null key; in that case, Kafka uses the default partitioner for keyless records.

## 4. Extracting the key from a custom header with messageKeyExpression

Sometimes the key is not inside the payload, or the application wants to keep the payload independent of routing logic. In that case, the producer can set a custom header and configure `messageKeyExpression` to read that header.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderEvent> message = MessageBuilder
        .withPayload(new OrderEvent(
                "ORD-1002",
                "CUS-02",
                "OrderPaid",
                2))
        .setHeader("customerKey", "CUS-02")
        .build();
~~~

Kafka Binder configuration:

This is an alternative to the payload-based key expression in the previous section; there is no need to configure two different key sources for the same binding.

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              messageKeyExpression: headers['customerKey']
              configuration:
                key.serializer: org.apache.kafka.common.serialization.StringSerializer
~~~

The binder reads `customerKey` from `MessageHeaders` and uses that value as the record key. The custom header only becomes the key because the expression references it. If you omit `messageKeyExpression`, `customerKey` is just regular metadata; it does not automatically replace the Kafka record key.

The expression can read other headers or combine SpEL logic. Make sure the header always exists, has a type supported by the key serializer, and does not unexpectedly return null. If a default value is needed, you can handle it when building the message or use a conditional expression, though key rules should remain consistent across producers.

## 5. Setting the key directly with KafkaHeaders.KEY

If the application already constructs a `Message<?>`, it can set the Kafka key using the dedicated `KafkaHeaders.KEY` header. This is convenient when the key is already available in Java code:

~~~java
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderEvent> message = MessageBuilder
        .withPayload(new OrderEvent(
                "ORD-1003",
                "CUS-03",
                "OrderShipped",
                3))
        .setHeader(KafkaHeaders.KEY, "ORD-1003")
        .build();
~~~

When using this dedicated header, the Kafka Binder can use its value as the record key without declaring `messageKeyExpression`. The key serializer configuration still needs to match the key's data type.

`KafkaHeaders.KEY` is the current constant name in Spring Kafka. In older versions, documentation and code may use `KafkaHeaders.MESSAGE_KEY`; the `MESSAGE_KEY` constant was deprecated in favor of `KEY` starting in Spring Kafka 2.9 and removed in newer versions. When upgrading, use the constant matching the Spring Kafka version in your project's dependencies.

Complete example using `StreamBridge`:

Declare the output binding to which the service will send:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderEvents-out-0:
          destination: orders.events
          content-type: application/json
      kafka:
        bindings:
          orderEvents-out-0:
            producer:
              configuration:
                key.serializer: org.apache.kafka.common.serialization.StringSerializer
~~~

~~~java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
class OrderEventPublisher {

    private final StreamBridge streamBridge;

    OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    boolean publish(OrderEvent event) {
        Message<OrderEvent> message = MessageBuilder
                .withPayload(event)
                .setHeader(KafkaHeaders.KEY, event.orderId())
                .build();

        return streamBridge.send("orderEvents-out-0", message);
    }
}
~~~

Here, `orderEvents-out-0` must be declared and mapped to the corresponding Kafka topic. The boolean return value of `send` indicates that the message was accepted via the binding/channel; it does not replace confirmation that the broker persisted the record or that a consumer finished processing it.

## 6. Choosing between messageKeyExpression and a Kafka header

Both approaches can produce the same record key. Choose the one that fits where the application holds the information:

| Scenario | Recommended approach |
|---|---|
| Key always comes from a payload field | messageKeyExpression: payload.orderId |
| Key is derived from metadata or a business header | messageKeyExpression: headers['customerKey'] |
| Java code explicitly builds Message<?> and knows the key | KafkaHeaders.KEY |
| Processing function wants to preserve the key received from Kafka | Copy the received key into the output header or use an expression reading the received key |
| Key needs to be determined by a centralized SpEL rule | messageKeyExpression |

Avoid configuring multiple conflicting key sources on the same binding. For example, if the payload has `orderId=ORD-1` while the `KafkaHeaders.KEY` header is `ORD-2`, readers will have trouble determining which business rule applies. Choose one canonical source and test the actual record key.

## 7. Preserving the key when a Function forwards messages

A processor can receive messages from an input topic and publish them to an output topic. To preserve the key, you can configure `messageKeyExpression` to read the incoming key header:

~~~yaml
spring:
  cloud:
    function:
      definition: forwardOrder
    stream:
      bindings:
        forwardOrder-in-0:
          destination: orders.in
          group: order-forwarder
        forwardOrder-out-0:
          destination: orders.out
      kafka:
        bindings:
          forwardOrder-out-0:
            producer:
              messageKeyExpression: headers['kafka_receivedMessageKey']
              configuration:
                key.serializer: org.apache.kafka.common.serialization.StringSerializer
~~~

The Kafka Binder places the received record key into the `kafka_receivedMessageKey` message header (the corresponding constant in current Spring Kafka is `KafkaHeaders.RECEIVED_KEY`). The expression reads this value to set the key for the output record.

For a standard `Function` processing messages, the configuration above is a concise way to forward the key. With a reactive function, the application needs to explicitly copy the header from the input message to the output message; do not assume all headers are automatically preserved when creating a new message.

The YAML snippet illustrates reading the received key via an expression. In the reactive function example below, the application explicitly sets `KafkaHeaders.KEY` on the output message; when using this approach, do not add `messageKeyExpression` to the same binding.

Example of a reactive function that explicitly preserves the key:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import reactor.core.publisher.Flux;

@Configuration
class OrderForwardingConfiguration {

    @Bean
    Function<Flux<Message<OrderEvent>>, Flux<Message<OrderEvent>>> forwardOrder() {
        return messages -> messages.map(input -> {
            OrderEvent output = transform(input.getPayload());

            return MessageBuilder.withPayload(output)
                    .setHeader(
                            KafkaHeaders.KEY,
                            input.getHeaders().get(KafkaHeaders.RECEIVED_KEY))
                    .build();
        });
    }
}
~~~

In this example, the key received from Kafka is placed back into the dedicated `KafkaHeaders.KEY` header of the output message. If you are using an older Spring Kafka version, the received key constant name may be `RECEIVED_MESSAGE_KEY`. Use the API matching your actual dependency and test after upgrading.

The `transform` method in the example represents the application's payload transformation logic; the main focus here is preserving the key while constructing the new message.

## 8. Distinguishing record key from partition-key-expression

Spring Cloud Stream has generic producer partitioning properties:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.events
          producer:
            partition-key-expression: payload.orderId
            partition-count: 12
~~~

`partition-key-expression` and `partition-count` belong to Spring Cloud Stream's partitioning mechanism. The binder uses the extracted key together with a partition selector to determine the target partition. With Kafka, topic partitioning is already natively supported by the broker; when binder partitioning is not used, the Kafka partitioner chooses the partition based on the record key.

`messageKeyExpression` is a Kafka Binder-specific property for creating the Kafka record key. The two properties have similar names, but their roles are not identical:

| Property | Role |
|---|---|
| partition-key-expression | Extracts the key for Spring Cloud Stream's generic partition selection mechanism |
| partition-count | Target partition count in binder partitioning; for Kafka, also acts as a provisioning hint |
| messageKeyExpression | Sets the key of the Kafka ProducerRecord |
| KafkaHeaders.KEY | Directly sets the key of the Kafka ProducerRecord |

If you only need Kafka to naturally select partitions by key, setting the record key via `messageKeyExpression` or `KafkaHeaders.KEY` is usually sufficient. If you need a custom binder partition selector, use `partition-key-expression` and configure the appropriate partition count. If the business logic needs both custom partition routing and a key stored on the record for compaction/consumer lookup, configure both explicitly and verify they do not conflict.

Do not confuse a record key with a partition ID. The key is a business value written alongside the record; the partition ID is the storage location selected by the producer or binder. Two records with different keys can still land in the same partition, and a single partition contains many keys.

## 9. Record key, Kafka headers, and header mapping

Kafka Headers are a set of byte-based key/value metadata attached to a record. They are distinct from the record key:

~~~text
Kafka record
  key: "ORD-1001"
  value: {...}
  headers:
    eventType: "OrderConfirmed"
    traceparent: "00-..."
    correlationId: "corr-81"
~~~

`KafkaHeaders.KEY` is a special Spring Messaging header used by the binder to set the record key. A custom header such as `customerKey` is only used as the record key when `messageKeyExpression` references it. Meanwhile, transferring custom headers to Kafka Headers is controlled by the header mapper and `headerPatterns`.

Example configuration allowing only specific custom headers to be propagated to Kafka:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              headerPatterns: eventType,correlationId,traceparent
~~~

`headerPatterns` controls which metadata headers are mapped to Kafka Headers; it does not replace `messageKeyExpression` and does not turn every header into a record key. You do not need to include the key in `headerPatterns` just to set the record key using `KafkaHeaders.KEY`.

## 10. Key serializers and data types

Kafka stores keys as bytes. The key serializer must be compatible with the Java type returned by the expression or header:

| Key type in application | Commonly used serializer |
|---|---|
| String | StringSerializer |
| byte[] | ByteArraySerializer |
| Integer | IntegerSerializer |
| Long | LongSerializer |

If `messageKeyExpression` returns a `String` while the key serializer is configured for another type, the producer may encounter serialization errors. For custom objects, a corresponding serializer and a clear decoding contract on the consumer side are required.

Example configuring a `Long` key:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          publishMetric-out-0:
            producer:
              messageKeyExpression: payload.accountNumber
              configuration:
                key.serializer: org.apache.kafka.common.serialization.LongSerializer
~~~

Ensure `accountNumber` is actually a `Long`, not a numeric string. Do not rely on implicit conversion between `String` and `Long`. When using native encoding, producers/consumers must configure matching serializers/deserializers for key and value; `content-type` does not replace native serializer configuration.

## 11. Version notes and expression evaluation order

Since Spring Cloud Stream Kafka Binder 3.0, `messageKeyExpression` is evaluated before the payload is converted to bytes. Therefore, the expression can read Java payload properties, such as `payload.orderId`, even when the binding uses a message converter. In versions prior to 3.0, the payload might already be a `byte[]` at the time the expression is evaluated; in that case, reading payload fields typically does not work unless native encoding is used. A more backward-compatible approach for older versions is to place the key in a header and read `headers['customerKey']`.

When upgrading Spring Cloud Stream or Spring Kafka:

- Verify compatible binder and Spring Kafka versions in dependency management.
- Use `KafkaHeaders.KEY` and `KafkaHeaders.RECEIVED_KEY` in current versions.
- Replace the legacy constants `MESSAGE_KEY` and `RECEIVED_MESSAGE_KEY` when the API removes them.
- Re-test `messageKeyExpression` expressions after changing message converters or native encoding.
- Verify that the actual producer is using the right key serializer.

Do not rely solely on the application starting successfully. A SpEL expression can be syntactically valid yet return null or the wrong type at runtime.

## 12. Inspecting the key on the consumer

A consumer can read the key sent by Kafka along with the record. With Spring Messaging, the Kafka Binder maps the received key to the `KafkaHeaders.RECEIVED_KEY` header:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;

@Configuration
class OrderAuditConfiguration {

    @Bean
    Consumer<Message<OrderEvent>> auditOrder() {
        return message -> {
            Object recordKey =
                    message.getHeaders().get(KafkaHeaders.RECEIVED_KEY);

            System.out.printf(
                    "key=%s order=%s event=%s%n",
                    recordKey,
                    message.getPayload().orderId(),
                    message.getPayload().eventType());
        };
    }
}
~~~

The consumer should verify that the key has the expected identifier and is consistent with the payload. If the key differs from `payload.orderId`, the producer may have used a different rule or the message may have been constructed incorrectly. In systems using multiple event types, the key may be a shared aggregate ID rather than a field with the same name across every payload; the contract should specify that clearly.

## 13. Keys and log compaction

A Kafka topic can use `cleanup.policy=compact` to retain the latest value per key during compaction. For example:

~~~text
key=ORD-1, value={status: CREATED}
key=ORD-2, value={status: CREATED}
key=ORD-1, value={status: PAID}
key=ORD-1, value={status: SHIPPED}
~~~

After compaction, Kafka can keep the latest record for `ORD-1` and `ORD-2` instead of every change for `ORD-1`. Therefore:

- Use a stable key representing the aggregate whose state needs to be retained.
- Do not use a random key if you want compaction to coalesce versions of the same entity.
- Use tombstones (a record with a key and a null value) according to Kafka conventions to represent key deletion.
- Do not use `compact` for an event log if consumers need to read the full history of all events.

Record keys also help consumers build keyed state and support querying/reconciliation. However, compaction is a background task; do not assume older records disappear immediately after a new record is written.

## 14. Common mistakes when choosing keys

| Symptom | Possible cause | Resolution |
|---|---|---|
| All records have a null key | Expression cannot read the field or header does not exist | Check SpEL, header name, and payload before sending |
| Key serialization error | Key type does not match key.serializer | Set the serializer matching the type or standardize the key type |
| Same entity goes to multiple partitions | Unstable key or producers use different rules | Normalize the key and unify the partitioner |
| Header has customerKey but record key is still null | Regular headers do not automatically become Kafka keys | Use messageKeyExpression or KafkaHeaders.KEY |
| Output key lost after Function | Function creates a new Message without copying/resetting the key | Copy the received header or set KafkaHeaders.KEY again |
| Consumer does not see the key | Reading the wrong metadata header or using an outdated constant API | Read KafkaHeaders.RECEIVED_KEY according to the current version |
| Skewed key distribution | Some aggregates produce far more messages than others | Measure key distribution; re-evaluate the key/sharding without breaking ordering requirements |

Do not use emails, phone numbers, access tokens, or sensitive data as raw keys unless necessary. Keys are stored with the record and can appear in admin tools, logs, or data replicas. Prefer stable internal IDs or pseudonymized values according to the system's data policy.

## 15. Testing message keys

The Spring Cloud Stream test binder is useful for testing function logic and bindings, but it does not always verify the actual key written by the Kafka producer. For critical requirements, use integration tests with a Kafka broker (such as Embedded Kafka or a containerized environment) and read `ConsumerRecord` to verify:

- Actual topic and partition.
- Record key after serialization/deserialization.
- Value and headers accompanying the record.
- Multiple events for the same aggregate share the same key and are written to the same partition when the partition count is unchanged.
- Forwarding functions preserve the incoming key accurately.
- Null or mistyped keys are caught according to policy.

When testing `messageKeyExpression`, include at least one test for a payload-derived key and one for a header-derived key. When testing `KafkaHeaders.KEY`, assert that `ConsumerRecord.key()` equals the expected value; do not check only `MessageHeaders` on the producer side.

## 16. Pre-release checklist

- Choose the key by the aggregate or entity that needs grouping, such as `orderId` or `accountId`.
- Clearly define whether the key comes from the payload, a custom header, or `KafkaHeaders.KEY`.
- If using `messageKeyExpression`, test the expression against the exact outgoing message.
- If using a Kafka header, set `KafkaHeaders.KEY` and use the API matching your Spring Kafka version.
- Set `key.serializer` to match the key's data type.
- Distinguish record keys from Kafka Headers and `partition-key-expression`.
- For forwarding `Function`s, explicitly preserve the incoming key.
- Check for null keys, mistyped keys, unstable keys, and skewed distribution.
- Verify the actual record key and partition using integration tests with Kafka.
- Evaluate the key's impact on ordering, log compaction, privacy, and hot partitions.

`messageKeyExpression` fits well when the key can be extracted from the payload or a header using SpEL. `KafkaHeaders.KEY` fits well when Java code wants to directly set the key for the Kafka record. Both approaches help Kafka route by key and group events for the same entity into one partition when the partitioning strategy is stable. Keep clear boundaries between record keys, Kafka headers, and binder partitioning; also verify serializers, API versions, and actual records to ensure the key is written according to the contract.

## References

- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — Kafka Tips and Tricks](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka_tips.html)
- [Spring Cloud Stream — Partitioning with the Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/partitions.html)
- [Spring for Apache Kafka — KafkaHeaders API](https://docs.spring.io/spring-kafka/docs/current/api/org/springframework/kafka/support/KafkaHeaders.html)

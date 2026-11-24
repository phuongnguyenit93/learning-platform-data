# Converters for ReplyingKafkaTemplate

Spring Kafka's `ReplyingKafkaTemplate` supports request/reply: the application sends a request to Kafka and then waits for a matching response from another listener. Each request is tagged with a correlation ID; the response must carry that correlation ID back so the template can find the waiting future. In this model, data can be sent and received as `ProducerRecord`/`ConsumerRecord`, or as Spring `Message<?>`.

When using the `Message<?>` API, `RecordMessageConverter` is the component that converts between Spring Messaging messages and Kafka records. The converter lets the application send a Java object as payload, maps Spring Message headers to Kafka headers, and converts the Kafka response back into a Spring Message. This is a conversion layer at the messaging boundary; Kafka `Serializer` and `Deserializer` remain responsible for converting Java keys/values to bytes and back.

This lesson focuses on configuring converters for `ReplyingKafkaTemplate`, using converters on the replying listener side, and preserving correlation/reply headers so requests match their responses accurately.

## 1. Request/reply flow in Spring Kafka

A request/reply flow typically has three components:

- **Requester**: application using `ReplyingKafkaTemplate` to send a request and wait for a response.
- **Responder**: listener receiving the request, processing it, and sending the response back to the reply topic.
- **Reply listener container**: consumer container used by `ReplyingKafkaTemplate` to receive responses and complete the corresponding future.

Processing flow:

```text
Requester application
      |
      | Message<OrderRequest>
      v
RecordMessageConverter
      |
      | ProducerRecord + correlation/reply headers
      v
Kafka request topic
      |
      v
Responder @KafkaListener
      |
      | convert request record -> Message/OrderRequest
      v
Business service processing
      |
      | OrderReply
      v
Reply converter + reply template
      |
      | response + correlation ID
      v
Kafka reply topic
      |
      v
Reply listener container
      |
      | look up future by correlation ID
      v
Requester receives Message<OrderReply>
```

`ReplyingKafkaTemplate` does not execute request business logic itself. It manages sending the request, registering the waiting future, receiving the response, and matching the response to the request via correlation ID. The responder listener is responsible for processing the request and publishing the response to the right topic/partition.

## 2. Distinguishing MessageConverter from Serializer/Deserializer

These two layers are often confused because both participate in data transformation:

| Component | Input/output | Responsibility |
|---|---|---|
| `RecordMessageConverter` | Spring `Message<?>` ↔ Kafka `ProducerRecord`/`ConsumerRecord` | Converts payloads and headers at the Spring message level |
| `MessagingMessageConverter` | Spring Message ↔ Kafka record | Foundational converter mapping payloads and headers; typically uses a header mapper |
| `JsonMessageConverter` and variants | Object ↔ JSON representation in Kafka record | Converts objects to JSON and back |
| Kafka `Serializer` | Java key/value → `byte[]` | Encodes key/value for transmission over the Kafka protocol |
| Kafka `Deserializer` | `byte[]` → Java key/value | Decodes key/value received from the broker |

For example, with `StringJsonMessageConverter`, an `OrderRequest` object is converted into a JSON string. `StringSerializer` then encodes the JSON string into bytes. On the receiving side, `StringDeserializer` reconstructs the JSON string and the converter transforms JSON into a Java object based on type metadata or the resolved target type.

```text
Message<OrderRequest>
       |
       v
StringJsonMessageConverter
       |
       v
String JSON
       |
       v
StringSerializer
       |
       v
byte[] in Kafka
```

If using `ByteArrayJsonMessageConverter`, the post-conversion payload is `byte[]`, so producer/consumer need matching byte array serializer/deserializer. Pair the converter and serializer together; do not configure a converter that produces `String` while using a serializer that only accepts `OrderRequest` or `byte[]`.

When passing a `ProducerRecord<K,V>` directly to `sendAndReceive(ProducerRecord)`, the Spring Message converter does not need to convert the request because the record already holds key/value in the right Java types. Kafka serializer/deserializer are still used. The converter becomes valuable when you want to use the `Message<?>` API and Spring headers.

## 3. RecordMessageConverter and JSON options

Spring Kafka defines `RecordMessageConverter` to convert between Spring Messages and Kafka records. Common implementations:

| Converter | Kafka payload representation | Matching serializer/deserializer |
|---|---|---|
| `MessagingMessageConverter` | Payload keeps its Java type before passing to Kafka serializer | Depends on configured serializer/deserializer |
| `StringJsonMessageConverter` | JSON as `String` | `StringSerializer` / `StringDeserializer` |
| `ByteArrayJsonMessageConverter` | JSON as `byte[]` | `ByteArraySerializer` / `ByteArrayDeserializer` |
| `BytesJsonMessageConverter` | JSON as Kafka `Bytes` | Matching serializer/deserializer for `Bytes` |

Class names and constructors may differ across Spring Kafka versions. The examples below use `StringJsonMessageConverter`, suitable when the application wants to store text JSON and use String serializer/deserializer. If your project uses another version, inspect the `org.springframework.kafka.support.converter` package and corresponding API.

Declaring the converter:

```java
@Configuration
public class KafkaMessageConversionConfiguration {

    @Bean
    public RecordMessageConverter requestReplyMessageConverter() {
        return new StringJsonMessageConverter();
    }
}
```

JSON converters can use type headers to identify the Java class when reading back. Align type mapping between requester and responder if the two applications use different packages/classes. Do not trust type headers coming from uncontrolled sources; configure trusted packages or token-based mappings matching your Spring Kafka version.

## 4. Configuring producer and reply consumer

In this example, the converter turns request/reply objects into JSON strings. Therefore, both the producer factory and the reply consumer factory use String serializer/deserializer:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
    consumer:
      group-id: order-reply-client-${INSTANCE_ID}
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      enable-auto-commit: false
      auto-offset-reset: latest
```

`auto-offset-reset: latest` is a common choice for a fresh reply container because the requester only needs responses emitted after it begins sending requests. However, the reply container must be started and receive partition assignment before sending requests; do not rely on `latest` to fix an unready reply container.

In applications with multiple requester instances, design reply topics, partitions, and consumer groups so responses reach the exact instance holding the waiting future. A shared group ID can cause replies to be distributed to another instance if topic/partition configuration is not designed appropriately. Typically, each requester instance has its own group ID or its own reply topic, and should be tested with multiple real instances.

## 5. Creating the reply listener container

`ReplyingKafkaTemplate` requires a listener container dedicated to receiving responses. This container is not a business `@KafkaListener`; the template registers itself as the container's message listener and processes responses based on correlation ID.

Example creating a container reading the `orders.replies` topic:

```java
@Configuration
public class ReplyContainerConfiguration {

    @Bean
    public ConcurrentMessageListenerContainer<String, String> repliesContainer(
            ConsumerFactory<String, String> consumerFactory,
            @Value("${spring.kafka.consumer.group-id}") String replyGroupId) {

        ContainerProperties properties =
                new ContainerProperties("orders.replies");
        properties.setGroupId(replyGroupId);

        return new ConcurrentMessageListenerContainer<>(
                consumerFactory, properties);
    }
}
```

`spring.kafka.consumer.group-id` must be given a valid value unique to the requester instance according to the deployment strategy. In the example, `INSTANCE_ID` is supplied per instance and Spring injects it into the group ID. You can use `ContainerProperties.setGroupId(...)` or configure the group ID on the consumer factory depending on configuration layout. Do not let multiple reply containers in the same group share a reply topic if each template can only complete futures belonging to the instance that sent the request.

The reply container must be started by the Spring lifecycle. If the application manages start/stop manually, ensure the container has received partition assignment before sending requests.

## 6. Creating ReplyingKafkaTemplate and attaching the converter

Once you have `ProducerFactory`, the reply container, and the converter, create the template:

```java
@Configuration
public class RequestReplyConfiguration {

    @Bean
    public ReplyingKafkaTemplate<String, String, String> replyingKafkaTemplate(
            ProducerFactory<String, String> producerFactory,
            ConcurrentMessageListenerContainer<String, String> repliesContainer,
            RecordMessageConverter requestReplyMessageConverter) {

        var template = new ReplyingKafkaTemplate<>(
                producerFactory, repliesContainer);
        template.setMessageConverter(requestReplyMessageConverter);
        template.setDefaultReplyTimeout(Duration.ofSeconds(10));
        return template;
    }
}
```

Here `K`, `V`, and `R` are all `String` because the converter uses JSON strings alongside String serializer/deserializer. `setMessageConverter(...)` enables the template's `Message<?>` API to convert request Spring Messages into Kafka records and convert reply records into Spring Messages. With the `ProducerRecord` API, data is already supplied as a Kafka record so no Spring Message conversion step occurs on the request.

`setDefaultReplyTimeout(...)` sets the default wait time for a response. You can use `sendAndReceive` overloads that accept a per-request timeout if supported by your Spring Kafka version. Timeout only limits how long to wait on the future; it does not cancel business logic already running on the responder and does not guarantee the request was not processed.

## 7. Sending a request using Spring Message

When using a converter, the requester can send a Spring `Message<OrderRequest>` instead of manually constructing a `ProducerRecord`:

```java
@Service
public class OrderQueryClient {

    private final ReplyingKafkaTemplate<String, String, String> template;

    public OrderQueryClient(
            ReplyingKafkaTemplate<String, String, String> template) {
        this.template = template;
    }

    public OrderReply findOrder(String orderId) throws Exception {
        Message<OrderRequest> request = MessageBuilder
                .withPayload(new OrderRequest(orderId))
                .setHeader(KafkaHeaders.TOPIC, "orders.requests")
                .setHeader(KafkaHeaders.MESSAGE_KEY, orderId)
                .build();

        RequestReplyMessageFuture<String, String, String> future =
                template.sendAndReceive(request);

        Message<?> replyMessage = future.get(10, TimeUnit.SECONDS);
        return (OrderReply) replyMessage.getPayload();
    }
}
```

`KafkaHeaders.TOPIC` specifies the request topic and `KafkaHeaders.MESSAGE_KEY` specifies the record key. `ReplyingKafkaTemplate` adds the correlation ID and reply topic/partition information needed for request/reply. The converter converts the `OrderRequest` payload into a JSON string before the Kafka producer serializer encodes it.

The example assumes the converter and type metadata are configured so the reply converts into `OrderReply`. In production code, check the returned payload type or use a wrapper/service layer to validate the type rather than blindly casting if multiple response types may appear.

Before sending the first request, you can wait for the reply container to be assigned partitions:

```java
if (!template.waitForAssignment(Duration.ofSeconds(10))) {
    throw new IllegalStateException("Reply container has not been assigned partitions");
}
```

Waiting for assignment helps avoid sending requests before the reply container is ready to receive responses. This API is available in modern Spring Kafka versions; if using a different version, check the corresponding container assignment verification mechanism.

## 8. Sending ProducerRecord when MessageConverter is not needed

If the application already constructs payloads as `String`, you can use `ProducerRecord` directly:

```java
ProducerRecord<String, String> request =
        new ProducerRecord<>("orders.requests", "order-42", "lookup:order-42");

RequestReplyFuture<String, String, String> future =
        template.sendAndReceive(request);

ConsumerRecord<String, String> reply =
        future.get(10, TimeUnit.SECONDS);

log.info("reply partition={}, offset={}, value={}",
        reply.partition(), reply.offset(), reply.value());
```

In this approach, the application is responsible for creating the payload string. Kafka serializer/deserializer convert strings to bytes and back. `RecordMessageConverter` does not automatically convert an arbitrary object to JSON in the `ProducerRecord` overload; if you want to send an object, either use `Message<?>` with a converter or serialize the object before building the record.

Using `ProducerRecord` is appropriate when direct control over topic, partition, timestamp, key, and Kafka headers is needed. Using `Message<?>` is appropriate when you want integration with Spring Messaging, `MessageBuilder`, header mapping, and automatic payload conversion.

## 9. Configuring the converter on the responder side

The responder receives the request record and sends the response. If you want the `@KafkaListener` method to receive `OrderRequest` instead of a JSON string, the listener container factory needs to use the same kind of converter:

```java
@Configuration
public class RequestListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, String>
            requestListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory,
                    KafkaTemplate<String, String> replyTemplate,
                    RecordMessageConverter requestReplyMessageConverter) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.setRecordMessageConverter(requestReplyMessageConverter);
        factory.setReplyTemplate(replyTemplate);
        return factory;
    }
}
```

`setRecordMessageConverter(...)` converts the request Kafka record into a Spring Message so the argument resolver can supply the payload according to the listener's parameter type. `setReplyTemplate(...)` provides the template used to send the listener's return value. The responder's `KafkaTemplate` needs a serializer compatible with the converter's output and must also have the same message converter attached so returned objects are converted into JSON strings:

```java
@Bean
public KafkaTemplate<String, String> replyTemplate(
        ProducerFactory<String, String> producerFactory,
        RecordMessageConverter requestReplyMessageConverter) {

    var template = new KafkaTemplate<>(producerFactory);
    template.setMessageConverter(requestReplyMessageConverter);
    return template;
}
```

The listener can return an object and use `@SendTo` without specifying a destination so Spring obtains the reply topic from the request header:

```java
@Component
public class OrderRequestListener {

    @KafkaListener(
            topics = "orders.requests",
            groupId = "orders-service",
            containerFactory = "requestListenerContainerFactory")
    @SendTo
    public OrderReply handle(OrderRequest request) {
        return orderService.find(request.orderId());
    }
}
```

In this request/reply flow, the request contains the reply topic header added by `ReplyingKafkaTemplate`. The listener container uses the reply template to send the return value to the designated topic/partition and preserves the correlation ID so the requester can match the response. If using a fixed `@SendTo("orders.replies")`, ensure that topic matches the requester's reply container and response routing strategy.

## 10. Correlation ID and reply headers

Request/reply needs to distinguish multiple concurrently waiting requests. `ReplyingKafkaTemplate` generates a correlation ID for each request and stores a mapping from that ID to the corresponding future. When a response returns, the template reads the correlation ID to complete the matching future.

Commonly used Spring Kafka headers:

| Header | Purpose |
|---|---|
| `KafkaHeaders.CORRELATION_ID` | Correlates the response with the original request |
| `KafkaHeaders.REPLY_TOPIC` | Tells the responder which reply topic to send to |
| `KafkaHeaders.REPLY_PARTITION` | Specifies the partition to receive the response when using partition-based routing |
| `KafkaHeaders.TOPIC` | Target topic of the request when creating a record from a Spring Message |
| `KafkaHeaders.MESSAGE_KEY` | Key of the Kafka record |

Do not strip correlation/reply headers when converting messages. If customizing `KafkaHeaderMapper`, make sure the necessary request/reply headers and type metadata are mapped across the Kafka record. A converter may transform the payload accurately, yet request/reply will still time out if the correlation ID or reply destination is lost.

If you need to change the correlation header name or ID generation strategy, `ReplyingKafkaTemplate` offers corresponding configuration options depending on the version. Only change them when both requester and responder agree on how headers are propagated back. The correlation ID is technical metadata for a single request call; do not use it as a substitute for an order or transaction business ID.

## 11. Converting type metadata across applications

JSON converters often rely on type headers to identify the Java class during deserialization. If the requester sends `com.example.client.OrderRequest` while the responder only has `com.example.server.OrderRequest`, relying directly on class names tightly couples the two applications' packages.

You can use stable token-based type mapping, such as `order-request` and `order-reply`, so each application maps tokens to its local classes. Exact configuration depends on the converter and Spring Kafka version; for JSON serializer/deserializer, properties like `spring.json.type.mapping`, default type, and trusted packages are commonly used. Ensure request and reply mappings align on both sides.

Do not confuse type metadata with schema version. A type ID answers which type the payload represents; schema version describes the structure of the payload in use. If the contract evolves over time, use an explicit version field or schema registry with dedicated compatibility rules.

When using a custom converter, you can explicitly set type headers or transform into an envelope containing `eventType` and `schemaVersion` fields. However, do not overwrite `KafkaHeaders.CORRELATION_ID`, `REPLY_TOPIC`, or `REPLY_PARTITION` when constructing responses.

## 12. Timeouts, send failures, and reply failures

`ReplyingKafkaTemplate` returns a future to track both the request send result and the response. You can inspect both stages separately:

```java
RequestReplyFuture<String, String, String> future =
        template.sendAndReceive(requestRecord);

SendResult<String, String> sendResult =
        future.getSendFuture().get(10, TimeUnit.SECONDS);

ConsumerRecord<String, String> replyRecord =
        future.get(10, TimeUnit.SECONDS);
```

`getSendFuture()` indicates whether the request was successfully sent by the producer. The main future completes when a matching response arrives or fails due to timeout/error. If sending fails, the responder never received the request. If sending succeeds but the future times out, the responder may still be processing, failed to send a reply, sent to the wrong topic/partition, or the response lost its correlation ID.

A timeout does not prove the business operation did not execute. The request may have been processed successfully while the response arrived late. If the requester retries after a timeout, the responder may execute the business operation twice. Use a business-level request ID/idempotency key to prevent duplicates; the correlation ID only matches responses to waiting calls.

For business errors, the responder can return a response representing the error rather than letting the request time out. Some Spring Kafka versions support `setReplyErrorChecker(...)` on the template to detect error responses from headers/payload and complete the future exceptionally. Check your version's API before using it; a simple and portable approach is defining `OrderReply` with `status`, `errorCode`, and `message` so the requester handles the outcome explicitly.

## 13. Multiple requester instances and reply partitions

In a multi-instance environment, each requester maintains a set of waiting futures in its own memory. Responses must be routed to the reply container of the instance that sent the request. If reply containers share groups and topics improperly, a response may be received by another instance; that instance has no matching correlation mapping, so the original requester's future will time out.

Common strategies:

1. Use a dedicated reply topic per requester instance.
2. Use a multi-partition reply topic with a shared consumer group; each requester selects only a partition assigned to its own reply container, and the responder sends to the partition specified in the reply partition header.
3. Use a separate group ID for each instance's reply container on a shared reply topic. Then every group may receive all responses on the topic; the template completes only futures with matching correlation IDs and ignores responses belonging to other instances. Account for traffic multiplying by the number of requester instances.

Do not pick a strategy based solely on partition count. Check `waitForAssignment()`, the partitions assigned to each reply container, and the reply topic/partition headers in requests. Test at least two requester instances sending requests concurrently to verify responses do not cross over.

## 14. Common pitfalls when using converters with ReplyingKafkaTemplate

| Symptom | Possible cause | Resolution |
|---|---|---|
| `ClassCastException` on send | Converter produces `String` while producer serializer expects a different object/byte array | Align converter output type with Kafka serializer |
| Listener fails to convert JSON to object | Converter is not attached to listener container factory or type metadata mismatches | Configure `setRecordMessageConverter()` and verify type mapping |
| Reply future times out even though responder processed it | Reply sent to wrong topic/partition or correlation header lost | Check `KafkaHeaders.REPLY_TOPIC`, `REPLY_PARTITION`, `CORRELATION_ID` |
| Future completes but payload has wrong type | Reply converter cannot infer type or responder sent wrong payload | Check JSON type headers, default type, and reply contract |
| Reply container not ready | Container not started or has not received partition assignment | Call `waitForAssignment()` before sending requests |
| Request sent successfully but no reply arrives | Listener errored, missing `@SendTo`, missing reply template, or reply send failed | Check responder logs, `setReplyTemplate()`, and reply topic |
| Random timeouts across multiple instances | Reply consumer group/partition routing sends responses to wrong instance | Design reply topic/partition and group ID per requester |
| Retrying after timeout causes duplicate side effects | Earlier request was processed but response arrived late | Use business request ID and idempotent handler |

## 15. Testing converters and the request/reply flow

Test two layers separately: conversion and request/reply integration.

### Converter unit tests

Verify that request objects convert into the expected record payload form and can be converted back into objects. With a JSON converter, check key fields, type metadata, and null handling. If using a custom header mapper, verify technical headers are preserved.

### Integration tests with test Kafka

An integration test should verify the entire flow:

1. Start the test broker and create request/reply topics.
2. Start the reply listener container and wait for assignment.
3. Start the responder listener with converter and reply template.
4. Send `Message<OrderRequest>` via `ReplyingKafkaTemplate`.
5. Verify the responder receives the expected `OrderRequest`.
6. Verify the response carries the matching correlation ID and the requester receives the expected `OrderReply`.
7. Test timeouts, send failures, error responses, and multiple concurrent requests.

Recommended test cases:

| Case | Expectation |
|---|---|
| Normal request/reply | Future completes with right response and payload type |
| Unicode request payload | JSON/string preserves Vietnamese characters intact |
| Missing responder | Future times out as configured |
| Reply missing correlation ID | Does not complete the wrong future; request times out and logs are traceable |
| Wrong reply topic/partition | Detected via timeout and header/assignment inspection |
| Multiple concurrent requests | Each future receives the matching response by correlation ID |
| Multiple requester instances | Responses arrive at the reply container of the requesting instance |
| Business error response | Requester receives error result or exception per contract |

## Production readiness checklist for request/reply

- Decided clearly between `Message<?>` + converter vs. direct `ProducerRecord`.
- Converter output type matches Kafka serializer/deserializer.
- Converter is configured on the requester template and responder listener container factory where needed.
- Reply container is started and assigned partitions before sending requests.
- Reply topic/partition and consumer group are designed so responses return to the right requester instance.
- Correlation ID, reply topic, and reply partition headers are preserved across converter/header mapper.
- Type mapping/trusted packages match the contract between requester and responder.
- Finite timeouts are set, and send failures are handled distinctly from reply timeouts.
- Requests include a business ID/idempotency key to prevent duplicate side effects when retrying after timeout.
- Integration tests cover concurrent requests, multiple instances, and error responses.

`RecordMessageConverter` lets `ReplyingKafkaTemplate` work naturally with Spring `Message<?>`, object payloads, and headers. For request/reply to work properly, converter, serializer/deserializer, type metadata, and correlation/reply headers must align on both sides. By additionally designing clear timeouts, routing, and idempotency, applications can use Kafka request/reply reliably.

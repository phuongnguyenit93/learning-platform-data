# Converting payloads by listener signature

With `@KafkaListener`, the method's parameter types determine at which level the application wants to receive data: the business payload, a Spring `Message<?>` with headers, or a Kafka `ConsumerRecord` containing full metadata. Spring Kafka can convert the record into the appropriate parameter type before invoking the method. This mechanism is called **message conversion**.

It is important to distinguish message conversion from deserialization. A deserializer converts Kafka bytes into an initial Java type; a message converter converts the deserialized data into the payload required by the listener signature. Understanding these two steps properly helps avoid duplicate configuration and handle errors at the right layer.

## 1. Two data conversion layers

Kafka stores keys and values as bytes. When a consumer reads a record, receiving data typically goes through two layers:

1. **Deserialization:** The Kafka `Deserializer` converts key/value bytes into an initial Java type, such as `byte[]`, `String`, or an object.
2. **Message conversion:** Spring Kafka `RecordMessageConverter` converts `ConsumerRecord` into a Spring `Message<?>` and can convert the payload into the type requested by the `@KafkaListener` method.

```mermaid
flowchart LR
    A[Kafka record: key/value bytes] --> B[Kafka Deserializer]
    B --> C[ConsumerRecord<K,V>]
    C --> D[Spring RecordMessageConverter]
    D --> E[Spring Message payload + headers]
    E --> F[@KafkaListener method parameter]
    F --> G[Business processing]
```

For example, a producer sends JSON bytes. There are two common ways for a listener to receive `OrderCreatedEvent`:

- Use `JsonDeserializer<OrderCreatedEvent>` to deserialize bytes directly into an object. In this case, the listener receives the payload object without needing a JSON message converter.
- Use `StringDeserializer` to receive JSON as a `String`, then use `StringJsonMessageConverter` to convert the JSON string into `OrderCreatedEvent` based on the listener parameter type.

Both approaches are valid, but you should choose one strategy clearly. Do not expect `StringDeserializer` to turn JSON into a POJO on its own, or configure `JsonDeserializer` and then add a converter to parse JSON a second time.

## 2. Listener signature determines the received data

Spring Kafka supports multiple parameter types. Each type fits a different level of data access:

| Method signature | Data received | When to use |
|---|---|---|
| `void listen(OrderCreatedEvent event)` | Business payload already deserialized/converted into an object. | Most listeners that only need to process business data. |
| `void listen(Message<OrderCreatedEvent> message)` | Payload object along with Spring Message headers. | Need payload and metadata as Spring headers. |
| `void listen(ConsumerRecord<String, OrderCreatedEvent> record)` | Kafka record with key, value, topic, partition, offset, timestamp, and Kafka headers. | Need low-level Kafka API or full metadata. |
| `void listen(String payload, @Header(...) String key)` | Payload along with selected individual headers. | Want a concise method and only need specific metadata. |

### Receiving the payload directly

This is the simplest form:

```java
@KafkaListener(topics = "orders.events", groupId = "order-projection")
public void onOrderCreated(OrderCreatedEvent event) {
    orderProjection.apply(event);
}
```

The `event` parameter is the payload produced after the deserializer or message converter runs. The method does not need to know which partition the record was stored in if business logic only cares about the event content.

### Receiving Spring Message to read headers

When both payload and metadata mapped to Spring Message headers are needed:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;

@KafkaListener(topics = "orders.events", groupId = "order-audit")
public void onOrderMessage(Message<OrderCreatedEvent> message) {
    OrderCreatedEvent event = message.getPayload();
    Object key = message.getHeaders().get(KafkaHeaders.RECEIVED_KEY);

    auditService.record(event, key);
}
```

Spring Kafka maps `ConsumerRecord` metadata into headers such as received topic, key, partition, offset, and timestamp. You can use `@Header` instead of accessing the map directly.

### Receiving ConsumerRecord

If native Kafka metadata is needed, accept `ConsumerRecord`:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;

@KafkaListener(topics = "orders.events", groupId = "order-monitor")
public void inspect(ConsumerRecord<String, OrderCreatedEvent> record) {
    log.info("topic={}, partition={}, offset={}, key={}",
            record.topic(),
            record.partition(),
            record.offset(),
            record.key());

    monitorService.observe(record.value());
}
```

In this signature, `record.value()` is the Java type returned by the Kafka value deserializer. `ConsumerRecord` is useful when direct access to Kafka metadata or headers is required; do not choose it just because you want to receive a simple POJO.

## 3. Using @Payload and @Header

A listener can receive the payload and explicitly specify which headers to extract:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@KafkaListener(topics = "orders.events", groupId = "order-projection")
public void onOrderCreated(
        @Payload OrderCreatedEvent event,
        @Header(KafkaHeaders.RECEIVED_KEY) String orderId,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset) {

    orderProjection.apply(event, orderId);
    log.debug("Handled orderId={} from partition={} offset={}",
            orderId, partition, offset);
}
```

`@Payload` marks the parameter holding the main content. `@Header` retrieves specific metadata from Spring Message headers. If a header may be absent or null in a data stream, use an appropriate nullable/wrapper type or declare `required = false` and a default value.

Commonly used Kafka headers:

| Header constant | Content |
|---|---|
| `KafkaHeaders.RECEIVED_TOPIC` | Name of the topic from which the record was received. |
| `KafkaHeaders.RECEIVED_KEY` | Key of the record. |
| `KafkaHeaders.RECEIVED_PARTITION` | Partition from which the record was received. |
| `KafkaHeaders.OFFSET` | Offset of the record. |
| `KafkaHeaders.RECEIVED_TIMESTAMP` | Timestamp received from the record. |

Header names and types may vary across Spring Kafka versions. When upgrading, check the Javadoc of `KafkaHeaders` matching your project's dependency.

## 4. When do you need RecordMessageConverter?

`RecordMessageConverter` is Spring Kafka's abstraction for converting between Kafka `ConsumerRecord`/`ProducerRecord` and Spring `Message<?>`. On the consumer side, the factory attaches a converter to convert received records into messages for method invocation.

Common implementations:

| Converter | Typical input data type | Role |
|---|---|---|
| `MessagingMessageConverter` | Payload already deserialized into a Java object. | Converts record into Spring Message and maps metadata to headers. |
| `StringJsonMessageConverter` | `String` from `StringDeserializer`. | Converts JSON string into the payload type per listener signature. |
| `ByteArrayJsonMessageConverter` | `byte[]` from `ByteArrayDeserializer`. | Converts JSON bytes directly into payload. |
| `BytesJsonMessageConverter` | Kafka `Bytes` from `BytesDeserializer`. | Converts Kafka Bytes into payload. |
| `JsonMessageConverter` | JSON value as String/byte[]/Bytes depending on supported configuration. | General-purpose JSON converter, usable directly or through specialized subclasses. |

If the value deserializer already produces the right POJO, the default `MessagingMessageConverter` usually only needs to wrap the payload and headers. If the deserializer returns a JSON `String` or bytes while the listener expects a POJO, use the corresponding JSON message converter.

## 5. Example: StringDeserializer combined with StringJsonMessageConverter

Suppose the producer sends JSON to the `orders.events` topic. The consumer uses `StringDeserializer`, so the initial value of `ConsumerRecord` is `String`. We want the listener method to receive `OrderCreatedEvent`.

### Consumer configuration

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-projection
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
```

### Container factory configuration

Since Spring Kafka 2.9.6, the factory provides `setRecordMessageConverter(...)`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.support.converter.StringJsonMessageConverter;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
    jsonListenerContainerFactory(
            ConsumerFactory<String, String> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.setRecordMessageConverter(new StringJsonMessageConverter());
        return factory;
    }
}
```

### Listener receiving POJO

```java
import org.springframework.kafka.annotation.KafkaListener;

@KafkaListener(
        topics = "orders.events",
        groupId = "order-projection",
        containerFactory = "jsonListenerContainerFactory"
)
public void onOrderCreated(OrderCreatedEvent event) {
    orderProjection.apply(event);
}
```

Here, the consumer factory still declares the value as `String`, matching `StringDeserializer`. The converter uses the `OrderCreatedEvent` parameter type of the method-level `@KafkaListener` as the target type, parsing the JSON string into an object before invoking the listener.

`setRecordMessageConverter(...)` has been available since Spring Kafka 2.9.6. Before that version, the factory used `setMessageConverter(...)`; the older API was replaced/deprecated to distinguish the converter for record listeners from the converter for batch listeners. Use the method present in your project's Spring Kafka version.

## 6. Alternative: JsonDeserializer converting straight to POJO

If conversion at the Spring Message layer is not needed, you can let Kafka `JsonDeserializer` create the object right during the deserialization step:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.orders.OrderCreatedEvent
        spring.json.trusted.packages: com.example.orders
```

Then the listener receives directly:

```java
@KafkaListener(topics = "orders.events", groupId = "order-projection")
public void onOrderCreated(OrderCreatedEvent event) {
    orderProjection.apply(event);
}
```

In this approach, `ConsumerRecord<String, OrderCreatedEvent>.value()` is already `OrderCreatedEvent`. There is no need to add `StringJsonMessageConverter` to parse JSON again.

The two strategies differ as follows:

| Criterion | `JsonDeserializer` | `StringJsonMessageConverter` |
|---|---|---|
| Where conversion happens | Inside Kafka consumer deserialization. | After the consumer has created `ConsumerRecord`, at the Spring Message conversion layer. |
| ConsumerRecord value type | POJO. | String. |
| Determining target type | Default type, type headers, or type resolver. | Can be inferred from the method-level `@KafkaListener` parameter. |
| Suitable when | Consumer has a known payload type and wants to receive objects immediately. | You want the listener signature to determine the target type or need Spring Message conversion. |

Do not configure `JsonDeserializer<OrderCreatedEvent>` and also declare a JSON converter to parse the value again. Choose one place responsible for turning JSON bytes into objects.

## 7. How parameter types affect type inference

When `@KafkaListener` is declared directly on a method, Spring Kafka can pass the parameter type to the converter to infer the target type. For instance, `OrderCreatedEvent` in the method signature is used to convert the JSON string into the corresponding object.

With a class-level `@KafkaListener` having multiple `@KafkaHandler` methods, the framework must determine which method to invoke based on the payload type. Therefore, the payload must be converted early enough to select the handler; it cannot always rely on an unselected method signature to infer the type. In this case, provide type information via headers/type mapping or configure an appropriate default type.

By default, JSON converters prioritize the type inferred from the method (`INFERRED`). You can configure the type mapper to prefer the type ID in headers (`TYPE_ID`) when using interfaces or multiple payload types. Only use type headers from trusted sources and align mappings between producer and consumer.

## 8. Receiving Spring Message and accessing metadata

Example listener receiving a Spring Message:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;

@KafkaListener(topics = "orders.events", groupId = "order-audit")
public void audit(Message<OrderCreatedEvent> message) {
    OrderCreatedEvent event = message.getPayload();

    String topic = message.getHeaders().get(KafkaHeaders.RECEIVED_TOPIC, String.class);
    Integer partition = message.getHeaders()
            .get(KafkaHeaders.RECEIVED_PARTITION, Integer.class);
    Long offset = message.getHeaders().get(KafkaHeaders.OFFSET, Long.class);

    auditService.record(event, topic, partition, offset);
}
```

The `Message<T>` type is useful when the method needs the payload together with multiple headers without depending directly on `ConsumerRecord`. If only one or two metadata fields are needed, `@Header` is usually more concise.

## 9. Batch listeners and list-shaped payloads

When the listener container is configured in batch mode, the method can receive `List<PayloadType>`. When JSON payloads start as String/bytes, use `BatchMessagingMessageConverter` combined with a matching record converter to convert each element.

Conceptual configuration example:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.support.converter.BatchMessagingMessageConverter;
import org.springframework.kafka.support.converter.StringJsonMessageConverter;

@Bean
ConcurrentKafkaListenerContainerFactory<String, String>
batchJsonListenerFactory(ConsumerFactory<String, String> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, String>();
    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setBatchMessageConverter(
            new BatchMessagingMessageConverter(new StringJsonMessageConverter())
    );
    return factory;
}
```

Listener receiving the list:

```java
import java.util.List;

import org.springframework.kafka.annotation.KafkaListener;

@KafkaListener(
        topics = "orders.events",
        groupId = "order-batch-projection",
        containerFactory = "batchJsonListenerFactory"
)
public void onOrders(List<OrderCreatedEvent> events) {
    events.forEach(orderProjection::apply);
}
```

Batch conversion has additional rules for per-element headers and errors. If per-record metadata is needed, you can receive a list of `Message<?>`, `ConsumerRecord<?, ?>`, or the batch headers supported by Spring Kafka. Verify the exact batch listener and converter types for your framework version.

## 10. Conversion errors and deserialization errors are different

The two error types occur at different times:

| Error type | Timing | Example | Related handling mechanism |
|---|---|---|---|
| Deserialization error | Before `poll()` returns the record to the listener container. | Malformed JSON bytes prevent `JsonDeserializer` from creating an object. | `ErrorHandlingDeserializer` stores error info in headers for the container/error handler to process. |
| Message conversion error | After `ConsumerRecord` exists, when the converter turns payload into listener parameter type. | JSON string cannot convert to `OrderCreatedEvent` due to mismatched field/type. | Listener container error handler handles exceptions thrown during listener invocation. |
| Business processing error | After payload is converted and listener method starts running. | Order not found or database temporarily unavailable. | Retry, error handler, DLT, or transaction according to application policy. |

`ErrorHandlingDeserializer` does not replace `RecordMessageConverter`. It handles errors at the Kafka deserialization layer; the converter handles errors at the Spring Message layer. Distinguishing them properly helps configure retries and dead-letter handling at the right place.

## 11. Common pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Listener receives `String` when expecting a POJO | Consumer uses `StringDeserializer` without configuring a JSON message converter. | Add `StringJsonMessageConverter` or switch to `JsonDeserializer`. |
| Deserialization fails before listener runs | `JsonDeserializer` cannot read bytes/schema/type header. | Check serializer, schema, default type, type mapping, and `ErrorHandlingDeserializer`. |
| Conversion error when invoking method | Converter does not support parameter type or JSON is incompatible with DTO. | Check method signature, converter, and actual JSON payload. |
| Converting JSON twice | Both using `JsonDeserializer` to create POJO and configuring a JSON message converter. | Pick a single layer to convert JSON to objects. |
| Cannot infer payload type | Using class-level `@KafkaListener` with multiple `@KafkaHandler`s without type information. | Supply type header/type mapping or configure target type. |
| Cannot access Kafka metadata | Method only accepts payload while trying to read undeclared metadata. | Accept `Message<T>`, `ConsumerRecord<K,V>`, or use `@Header`. |
| Batch listener receives wrong type | Factory has not enabled batch mode or batch converter is mismatched. | Align `setBatchListener(true)`, converter, and collection parameter type. |
| Header type incompatible across services | Producer and consumer use different class/package names. | Use stable type mapping or a schema contract independent of class names. |

## 12. Testing conversion by listener signature

Integration tests should verify that the payload arrives as the exact type requested by the method, while also checking metadata if the listener accepts `Message<?>` or `ConsumerRecord`.

For the `StringDeserializer` + `StringJsonMessageConverter` strategy, verify:

1. Producer sends a JSON string to the topic.
2. Consumer factory uses `StringDeserializer` for value.
3. Listener method receives `OrderCreatedEvent`, not a JSON string.
4. Fields such as `eventId`, `orderId`, `total` hold expected values.
5. Malformed JSON triggers the configured error handler and retry/DLT.

For the `JsonDeserializer` strategy, specifically verify that type headers/default types resolve properly and the listener receives the object directly. Do not test only the converter in isolation; include at least one integration test through the listener container to verify the full pipeline.

## 13. Key takeaways

- Deserializers convert Kafka bytes into an initial Java type; message converters convert records/messages into payloads matching the listener signature.
- Listeners receive the payload directly when only business data is needed.
- Use `Message<T>` to receive payload plus Spring headers; use `ConsumerRecord<K,V>` for full Kafka metadata access.
- `@Payload` and `@Header` clearly select the required payload and metadata.
- `JsonDeserializer` builds the POJO directly at the deserialization layer; `StringJsonMessageConverter` converts JSON String into the listener parameter type at the message conversion layer.
- `RecordMessageConverter` can infer target types from method-level `@KafkaListener`; class-level `@KafkaListener` with `@KafkaHandler` requires type information before dispatch.
- Batch listeners require an appropriate batch converter if each element in the list needs conversion.
- Deserialization errors, conversion errors, and business processing errors occur at different stages and must be handled at the right layer.

When choosing a `@KafkaListener` signature, start from what the method actually needs: payload, headers, or Kafka record. Then determine what initial Java type the deserializer produces and whether a message converter is needed to convert it further. Consistent configuration across both layers ensures listeners receive the right data types and errors are handled in the proper place.

## References

- [Spring for Apache Kafka — Serialization, Deserialization, and Message Conversion](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html)
- [Spring Kafka — RecordMessageConverter API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/support/converter/RecordMessageConverter.html)
- [Spring Kafka — JsonMessageConverter API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/support/converter/JsonMessageConverter.html)
- [Spring for Apache Kafka — @KafkaListener Annotation](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/listener-annotation.html)

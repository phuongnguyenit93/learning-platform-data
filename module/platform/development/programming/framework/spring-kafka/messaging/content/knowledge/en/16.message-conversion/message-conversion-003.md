# RecordMessageConverter

Kafka stores keys and values as byte arrays, while Spring applications typically work with DTOs, objects, and `Message<?>`. `RecordMessageConverter` is the bridge between these two models at the Spring Messaging layer: it converts a Kafka record into a Spring `Message` when the consumer receives data, and converts a Spring `Message` into a Kafka `ProducerRecord` when the producer sends a message.

An important point is that `RecordMessageConverter` does not replace Kafka `Serializer`/`Deserializer`. Serializers and deserializers are responsible for converting Java types to bytes and back in the Kafka client. The message converter organizes the payload along with metadata into Spring's abstraction, and can also perform payload conversion such as JSON when configured appropriately.

## 1. Where does RecordMessageConverter sit?

Spring Kafka combines the Kafka client API with Spring Messaging. On the receiving side, the Kafka consumer returns a `ConsumerRecord`; the listener adapter can use a converter to create a `Message<?>` and then invoke the `@KafkaListener` method. On the sending side, `KafkaTemplate.send(Message<?>)` uses the converter to build a `ProducerRecord` before handing it to the Kafka producer.

```text
Consumer side
Kafka broker
    |
    v
KafkaConsumer
    |
    v
ConsumerRecord<K, V>
    |
    v
RecordMessageConverter
    |
    v
Spring Message<?>
    |
    v
@KafkaListener

Producer side
Spring Message<?>
    |
    v
KafkaTemplate.send(Message<?>)
    |
    v
RecordMessageConverter
    |
    v
ProducerRecord<K, V>
    |
    v
KafkaProducer + Serializer
    |
    v
Kafka broker
```

The converter can participate in both directions, but only when the application uses the corresponding API. For example, `KafkaTemplate.send(topic, key, value)` sends key/value directly through the Kafka serializer; that call does not need to convert a `Message<?>` via `RecordMessageConverter`.

## 2. Distinguishing Serializer, Deserializer, and Message Converter

Three components often appear together but address different layers:

| Component | Input | Output | Role |
| --- | --- | --- | --- |
| Kafka `Serializer` | Java key/value | `byte[]` | Encodes key/value before the producer sends |
| Kafka `Deserializer` | `byte[]` | Java key/value | Decodes key/value after the consumer receives |
| Spring `RecordMessageConverter` | Kafka record or Spring `Message<?>` | Spring `Message<?>` or Kafka `ProducerRecord` | Converts between Kafka records and the Spring Messaging abstraction |

The first example uses `JsonSerializer`/`JsonDeserializer`: the producer serializes the DTO into JSON bytes, and the consumer deserializes JSON bytes into the DTO. The listener can receive the DTO directly; the default converter mainly helps map the record and metadata into a Spring message if the listener uses `Message<?>`.

The second example uses `StringSerializer`/`StringDeserializer` together with `StringJacksonJsonMessageConverter` on Spring Kafka 4.x: the Kafka client transports JSON as a `String`, while the message converter turns the JSON string into a DTO based on the payload type requested by the listener. For Spring Kafka 3.x and earlier, use `StringJsonMessageConverter`. Both approaches can use JSON, but they place the JSON conversion step at two different layers.

Do not configure two JSON mechanisms in an overlapping way without understanding the conversion order. If `JsonDeserializer` already returns `OrderCreatedEvent`, you do not need another JSON converter to parse that object again.

## 3. The default RecordMessageConverter

Spring Kafka provides `MessagingMessageConverter` as the foundational converter. It converts a `ConsumerRecord` into a Spring `Message<?>`, maps key metadata into message headers, and converts a Spring message into a `ProducerRecord` when sending.

On the receiving side, the payload is typically the value already produced by the Kafka deserializer. The converter adds Spring Kafka headers such as:

| Header | Meaning |
| --- | --- |
| `KafkaHeaders.RECEIVED_TOPIC` | Topic from which the record was received |
| `KafkaHeaders.RECEIVED_PARTITION` | Partition from which the record was received |
| `KafkaHeaders.OFFSET` | Offset of the record |
| `KafkaHeaders.RECEIVED_KEY` | Received key |
| `KafkaHeaders.RECEIVED_TIMESTAMP` | Timestamp of the record |
| `KafkaHeaders.TIMESTAMP_TYPE` | Timestamp type |
| `KafkaHeaders.GROUP_ID` | Consumer group of the listener container |

The exact headers may depend on version and listener type. `RECEIVED_KEY` and `RECEIVED_PARTITION` are the modern names since Spring Kafka 2.9; older versions used `RECEIVED_MESSAGE_KEY` and `RECEIVED_PARTITION_ID`. When the full Kafka API is needed, you can accept `ConsumerRecord<K, V>` directly instead of relying on Spring headers.

In Spring Kafka 2.5 and later, the `RECEIVED_KEY` header is not added if the record has a `null` key; therefore, mark it `required = false` or use a nullable type when binding the key.

## 4. Receiving Spring Message in @KafkaListener

Instead of only accepting a payload DTO, a listener can accept `Message<T>` to access both payload and headers:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;
import com.example.messaging.event.OrderCreatedEvent;

@Component
public class OrderMessageListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "order-projection")
    public void onMessage(Message<OrderCreatedEvent> message) {
        OrderCreatedEvent event = message.getPayload();
        String topic = message.getHeaders()
                .get(KafkaHeaders.RECEIVED_TOPIC, String.class);
        Integer partition = message.getHeaders()
                .get(KafkaHeaders.RECEIVED_PARTITION, Integer.class);
        Long offset = message.getHeaders()
                .get(KafkaHeaders.OFFSET, Long.class);

        // Process event and use metadata for tracing.
    }
}
```

For `Message<OrderCreatedEvent>` to have a DTO payload, the consumer needs to use `JsonDeserializer` or configure a JSON `RecordMessageConverter` as shown in later sections; the default `MessagingMessageConverter` only wraps the value returned by the Kafka deserializer and maps metadata. `Message<T>` is useful when the method needs the payload together with correlation ID, topic, partition, or offset. If only the payload is needed, accepting `OrderCreatedEvent` directly is more concise. If all record details or the consumer API are needed, accept `ConsumerRecord<K, V>`.

You can bind a single header using `@Header`:

```java
@KafkaListener(topics = "orders.created", groupId = "order-projection")
public void onMessage(
        OrderCreatedEvent event,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset) {
    // Use event, partition, and offset.
}
```

The example needs to import `org.springframework.messaging.handler.annotation.Header`. Choose a header data type matching the value supplied by the converter; if the header may be absent, use a nullable type such as `Integer` or `Long` and check for null.

## 5. Sending Spring Message with KafkaTemplate

`KafkaTemplate` has a `send(Message<?>)` overload. The converter configured on the template reads the payload and headers of the Spring message to create a Kafka `ProducerRecord`.

Example:

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String orderId, String json) {
        Message<String> message = MessageBuilder
                .withPayload(json)
                .setHeader(KafkaHeaders.TOPIC, "orders.created")
                .setHeader(KafkaHeaders.KEY, orderId)
                .setHeader("correlationId", "corr-42")
                .build();

        kafkaTemplate.send(message);
    }
}
```

In the example, `KafkaHeaders.TOPIC` specifies the destination topic and `KafkaHeaders.KEY` specifies the key. Since Spring Kafka 2.9, `KEY` is the modern header name; older versions used `MESSAGE_KEY`. The converter maps supported headers into Kafka record metadata. The `correlationId` header is application metadata and must be supported by the header mapper to be transferred as a Kafka header.

If there is no topic in the message headers, the template must have an appropriate default topic; if neither is present, the destination cannot be determined. When you need control over partition, timestamp, or specific Kafka metadata, you can build a `ProducerRecord` directly or use the `KafkaTemplate.send(topic, partition, key, value)` overload.

## 6. JSON Message Converters

When the Kafka client uses `StringDeserializer` or a byte deserializer, the payload arriving from Kafka can be a JSON string/bytes. Spring Kafka provides JSON message converters to convert this payload into the Java type requested by the listener.

Common converters include:

| Converter | JSON payload type at the Kafka client layer |
| --- | --- |
| `StringJacksonJsonMessageConverter` | `String` |
| `ByteArrayJacksonJsonMessageConverter` | `byte[]` |
| `BytesJacksonJsonMessageConverter` | Kafka `Bytes` |

With Spring Kafka 4.x, use converters based on Jackson 3. Example using `StringJacksonJsonMessageConverter`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.support.converter.RecordMessageConverter;
import org.springframework.kafka.support.converter.StringJacksonJsonMessageConverter;

@Bean
public RecordMessageConverter recordMessageConverter() {
    return new StringJacksonJsonMessageConverter();
}
```

When a listener requests `OrderCreatedEvent`, the converter reads the JSON string and converts it into the DTO. On the sending side, the converter can turn a payload object into a JSON string so `StringSerializer` encodes it into bytes.

JSON converters use Jackson. In Spring Kafka 4.0 and later, `JacksonJsonMessageConverter` is the base class using Jackson 3; `StringJacksonJsonMessageConverter`, `ByteArrayJacksonJsonMessageConverter`, and `BytesJacksonJsonMessageConverter` select the appropriate value type for the producer. The legacy names `StringJsonMessageConverter`, `ByteArrayJsonMessageConverter`, and `BytesJsonMessageConverter` belong to the Jackson 2 generation and have been deprecated since Spring Kafka 4.0 in favor of the new classes. For Spring Kafka 3.x and earlier, use the converter names corresponding to that version.

`byte[]` and Kafka `Bytes` avoid the intermediate `String` ↔ `byte[]` conversion step, so they can be more efficient for large payloads or high throughput. The payload type is typically inferred from the parameter on a method-level `@KafkaListener`. For a class-level `@KafkaListener` with multiple `@KafkaHandler` methods, the payload must be converted early enough for the framework to choose the right handler.

## 7. Configuring the converter for the listener container

To make the listener container use a custom converter, set `RecordMessageConverter` on `ConcurrentKafkaListenerContainerFactory`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.support.converter.RecordMessageConverter;
import org.springframework.kafka.support.converter.StringJacksonJsonMessageConverter;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public RecordMessageConverter recordMessageConverter() {
        return new StringJacksonJsonMessageConverter();
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, String>
            kafkaListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory,
                    RecordMessageConverter recordMessageConverter) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.setRecordMessageConverter(recordMessageConverter);
        return factory;
    }
}
```

With this configuration, `ConsumerFactory<String, String>` must use `StringDeserializer` for the value. The converter receives a JSON String and converts it into a DTO matching the listener parameter type. When using `JsonDeserializer` which already creates the DTO, configuring a JSON converter like above is usually unnecessary; you can keep the default converter to map records into Spring `Message`s.

If the application uses Spring Boot auto-configuration, you can declare a converter bean and configure the Boot-created listener factory according to the mechanism of the version in use. When declaring the factory manually, attach the converter directly as in the example to know for certain which listener containers use that converter.

## 8. Configuring the converter for KafkaTemplate

`KafkaTemplate` can also use `RecordMessageConverter` to support `send(Message<?>)`:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.converter.RecordMessageConverter;
import org.springframework.kafka.support.converter.StringJacksonJsonMessageConverter;

@Configuration
public class KafkaTemplateConfiguration {

    @Bean
    public RecordMessageConverter outboundMessageConverter() {
        return new StringJacksonJsonMessageConverter();
    }

    @Bean
    public KafkaTemplate<String, String> kafkaTemplate(
            ProducerFactory<String, String> producerFactory,
            @Qualifier("outboundMessageConverter")
            RecordMessageConverter outboundMessageConverter) {

        KafkaTemplate<String, String> template =
                new KafkaTemplate<>(producerFactory);
        template.setMessageConverter(outboundMessageConverter);
        return template;
    }
}
```

`ProducerFactory<String, String>` in the example must use `StringSerializer` for both key and value because the JSON converter produces a String value. If the producer factory uses `JsonSerializer`, consider sending the DTO directly via `send(topic, key, value)` instead of serializing JSON a second time through the converter.

In real-world projects, you can use a shared converter bean for both inbound and outbound if they share compatible settings. If the two directions require different conversion behavior, declare separate beans and wire the right bean into the corresponding listener factory or template.

## 9. Header mapping between Spring Message and Kafka record

Spring `Message<?>` uses `MessageHeaders`; Kafka records use `Headers`, where each header has a name and a byte value. `MessagingMessageConverter` uses a header mapper to convert between the two formats.

Spring Kafka provides common header mappers:

- `JsonKafkaHeaderMapper`: the default JSON header mapper in Spring Kafka 4.x, supporting header data type conversion and type metadata via Jackson 3.
- `SimpleKafkaHeaderMapper`: maps raw headers as `byte[]`; can be configured to convert certain String headers using a charset, without using JSON to restore rich Java types.

When Jackson is on the classpath, Spring Kafka 4.x defaults to `JsonKafkaHeaderMapper` in `MessagingMessageConverter`. Without a header mapper, native Kafka headers can be placed into the message under `KafkaHeaders.NATIVE_HEADERS`.

Example configuring a mapper:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.support.JsonKafkaHeaderMapper;
import org.springframework.kafka.support.converter.MessagingMessageConverter;

@Bean
public MessagingMessageConverter messagingMessageConverter() {
    MessagingMessageConverter converter =
            new MessagingMessageConverter();
    converter.setHeaderMapper(new JsonKafkaHeaderMapper());
    return converter;
}
```

In Spring Kafka 3.x and earlier, the corresponding JSON mapper name is `DefaultKafkaHeaderMapper`; that class has been deprecated since 4.0 in favor of `JsonKafkaHeaderMapper`. When only a subset of headers should pass through, configure header mapper patterns following a naming convention. This helps prevent accidentally sending internal Spring headers or sensitive data to Kafka.

`JsonKafkaHeaderMapper` uses JSON to preserve types of complex headers and writes type metadata into a special header. Only trust the necessary packages when restoring header types; avoid opening a wildcard for all packages if messages come from sources that are not fully trusted. Headers with untrusted types may be returned as unverified type information instead of the original Java object.

Not every Spring message header is converted into a Kafka header. Some internal framework headers, unserializable headers, or headers excluded by patterns will not be mapped. Test the headers the application needs to transmit through the broker instead of assuming all `MessageHeaders` are preserved.

## 10. Standard headers and business headers

Distinguish metadata supplied by Kafka from business headers created by the application:

| Category | Examples | Source |
| --- | --- | --- |
| Inbound Kafka metadata | `RECEIVED_TOPIC`, `RECEIVED_PARTITION`, `OFFSET`, `RECEIVED_TIMESTAMP` | Kafka record and listener container |
| Outbound Kafka metadata | `TOPIC`, `PARTITION`, `KEY`, `TIMESTAMP` | Spring message sent via KafkaTemplate |
| Business headers | `correlationId`, `eventType`, `traceId`, `sourceService` | Application |

Example reading a correlation ID:

```java
@KafkaListener(topics = "orders.created", groupId = "order-projection")
public void onMessage(
        OrderCreatedEvent event,
        @Header(name = "correlationId", required = false) String correlationId) {
    // Attach correlationId to logs or traces.
}
```

Business headers need stable naming conventions, encodings, and semantics between producer and consumer. Do not put large data in headers; the payload should hold the main business data. Do not use headers to pass passwords, tokens, or secrets.

## 11. RecordMessageConverter and BatchMessageConverter

`RecordMessageConverter` processes one Kafka record at a time. When a listener is configured in batch mode and receives a set of records from a single poll, Spring Kafka uses the `BatchMessageConverter` abstraction.

`BatchMessagingMessageConverter` is the common batch converter. It can use a `RecordMessageConverter` to convert each record in the batch before building a Spring message containing a list of payloads.

Configuration example:

```java
import org.springframework.kafka.support.converter.BatchMessagingMessageConverter;
import org.springframework.kafka.support.converter.RecordMessageConverter;

var batchConverter =
        new BatchMessagingMessageConverter(recordMessageConverter);
factory.setBatchMessageConverter(batchConverter);
factory.setBatchListener(true);
```

With a batch listener, the method can receive `List<OrderCreatedEvent>` or `Message<List<OrderCreatedEvent>>` depending on configuration and converter type. If per-record metadata is needed, use the appropriate batch converter mode and inspect the batch headers provided by Spring Kafka. Do not attach `RecordMessageConverter` as though it handles an entire batch on its own; the listener factory has a separate batch converter setting.

## 12. When should you use RecordMessageConverter?

| Need | Suitable choice |
| --- | --- |
| Listener needs payload and metadata as a Spring abstraction | Default `RecordMessageConverter` and `Message<T>` parameter |
| Want to receive a DTO from a JSON String | `StringJacksonJsonMessageConverter` with `StringDeserializer` on Spring Kafka 4.x; use the corresponding converter on older versions |
| Want to send a Spring `Message<?>` via KafkaTemplate | Configure a converter on `KafkaTemplate` |
| Already using `JsonSerializer`/`JsonDeserializer` for DTOs | Use serializer/deserializer; default converter is only needed when Spring Message/header mapping is required |
| Need to read all Kafka record properties directly | Accept `ConsumerRecord<K, V>` |
| Listener receives a list of records from a poll | `BatchMessageConverter` and batch listener |
| Convert payload using custom domain rules | Customize `RecordMessageConverter` or use a specialized converter |

There is no need to add a JSON converter if the serializer/deserializer already handles the payload. The converter is most useful when the application wants to work with Spring `Message<?>`, map metadata, or convert JSON payloads at the Spring Messaging layer.

## 13. Customizing RecordMessageConverter

When conversion rules do not fit built-in converters, you can extend `MessagingMessageConverter` or implement `RecordMessageConverter`. Example customization needs:

- Mapping a proprietary header into standard application metadata.
- Normalizing legacy payloads before the listener receives them.
- Adding correlation or source headers to records when sending.
- Transforming payloads into a shared domain envelope.

When customizing, keep both conversion directions clear:

1. `ConsumerRecord` to Spring `Message<?>`: determine payload type, map metadata, and handle nulls.
2. Spring `Message<?>` to `ProducerRecord`: determine topic, key, partition, timestamp, payload, and headers.

Do not place business logic such as database updates, permission checks, or external service calls inside a converter. The converter should focus on data representation conversion; business logic belongs in the listener or application service. This keeps the converter easy to test and reuse.

If implementing a custom converter, pay attention that the payload type may be generic or parameterized, headers may be missing or have unexpected types, and the serializer must still be compatible with the value type produced by the converter.

## 14. SmartMessageConverter and Content-Type

`RecordMessageConverter` can delegate payload conversion to a Spring `SmartMessageConverter`. This is useful when you want to choose how to read the payload based on `MessageHeaders.CONTENT_TYPE`, such as JSON or another media type, while still using the same Kafka record and header mapping mechanism.

For `KafkaTemplate`, you can attach a `SmartMessageConverter` with `setMessagingConverter(...)`. For `@KafkaListener`, you can specify a converter bean via the annotation's `contentTypeConverter` attribute:

```java
@KafkaListener(
        id = "content-aware-listener",
        topics = "integration.events",
        contentTypeConverter = "eventContentConverter")
public void listen(OrderCreatedEvent event) {
    // Payload has been converted according to the appropriate content type.
}
```

The `eventContentConverter` bean must implement `SmartMessageConverter` and be registered in the Spring context. The converter must handle the payload type and content type sent by the producer. If the converter returns `null`, Spring Kafka retains the original message/payload as a fallback; therefore, test both supported content types and mismatched cases.

## 15. Testing message conversion

Converter tests should verify both payload and metadata in both directions.

### Testing receiving a record as a Spring Message

Create a `ConsumerRecord` with test topic, partition, offset, key, value, and headers, then invoke the converter to verify payload/headers. When using a JSON converter, check that the resulting DTO has the expected fields.

### Testing sending a Spring Message as a ProducerRecord

Build a message with `MessageBuilder`, setting `KafkaHeaders.TOPIC`, key, and custom headers. Invoke the converter and verify that topic, key, payload, and headers are mapped as expected.

Conceptual outbound test example:

```java
Message<String> message = MessageBuilder
        .withPayload("{\"orderId\":\"ORD-42\"}")
        .setHeader(KafkaHeaders.TOPIC, "orders.created")
        .setHeader(KafkaHeaders.KEY, "ORD-42")
        .build();

ProducerRecord<?, ?> record = converter.fromMessage(message, null);

assertThat(record.topic()).isEqualTo("orders.created");
assertThat(record.key()).isEqualTo("ORD-42");
```

The test snippet requires an appropriate converter and imports for `ProducerRecord`, `KafkaHeaders`, `Message`, `MessageBuilder`, and the assertion library. Depending on the converter and configuration, the `ProducerRecord` payload may be a String, byte array, or object; assertions must reflect the value type the serializer will receive.

### Integration testing with a broker

In integration tests, send a `Message<?>` through `KafkaTemplate`, receive it with `@KafkaListener`, and verify:

1. Topic/key/partition are mapped properly.
2. JSON payload is converted into the expected DTO.
3. Custom headers are sent and received with the proper encoding.
4. Inbound metadata such as topic/partition/offset appear in Spring Message headers.
5. Conversion errors are routed to the error handler as configured.

Test both the direct serializer/deserializer path and the message converter path if the application supports both. This helps avoid duplicate configuration where payloads are serialized twice or the converter receives the wrong data type.

## 16. Common pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Listener receives JSON String instead of DTO | Using `StringDeserializer` without configuring a JSON converter, or method signature does not request DTO | Configure `StringJacksonJsonMessageConverter` on Spring Kafka 4.x or use `JsonDeserializer` |
| JSON parsed twice or type error | Combining `JsonDeserializer` with an incompatible JSON message converter | Choose a single layer responsible for deserializing JSON |
| `KafkaTemplate.send(Message<?>)` reports missing topic | Message lacks `KafkaHeaders.TOPIC` and template has no default topic | Set the topic header or default topic |
| Custom header does not reach consumer | Header mapper does not map that name/type | Configure `JsonKafkaHeaderMapper` (Spring Kafka 4.x) or `DefaultKafkaHeaderMapper` (3.x and earlier), patterns, and encoding |
| Received header has unexpected type | Kafka header is byte[] or mapper converted the type | Standardize types and encoding between producer/consumer |
| Batch listener does not convert payload as expected | `BatchMessageConverter` not configured or factory has not enabled batch mode | Configure batch converter and `setBatchListener(true)` |
| Converter does not run with `send(topic, key, value)` | That API uses the serializer directly, bypassing `send(Message<?>)` | Use `send(Message<?>)` or convert the payload before calling send |
| Converter contains business logic hard to test | Mixing data conversion with business processing | Move business logic into listener/service, keep converter focused on mapping |

## 17. Conclusion

`RecordMessageConverter` converts between Kafka records and Spring `Message<?>`. On the consumer side, it lets listeners receive payloads along with metadata as Spring headers. On the producer side, it enables `KafkaTemplate.send(Message<?>)` to convert payloads and headers into a `ProducerRecord`.

Distinguish message converters from Kafka serializers/deserializers: serializers/deserializers work with bytes in the Kafka client, while converters work at the Spring Messaging layer. Use `MessagingMessageConverter` for standard record/header mapping, a JSON converter when you want to convert JSON Strings/bytes into DTOs at the message layer, and `BatchMessageConverter` for batch listeners. Pick exactly one layer responsible for JSON conversion, configure the header mapper intentionally, and keep business logic outside converters so Spring Kafka flows stay easy to understand, test, and operate.

## References

- [Spring for Apache Kafka — Message Conversion](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html)
- [Spring for Apache Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring for Apache Kafka — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
- [Spring for Apache Kafka — Kafka Headers](https://docs.spring.io/spring-kafka/reference/kafka/headers.html)

# MessagingMessageConverter in Spring Kafka

`MessagingMessageConverter` is a converter at the Spring Messaging layer that connects a Kafka record with `Message<?>`. It converts a `ConsumerRecord` into a Spring Message when the consumer receives data and converts a Spring Message into a `ProducerRecord` when the producer sends data using `KafkaTemplate`'s message API.

This converter helps applications work with payloads and headers following the `Message<?>` model, instead of manually reading every field of a `ConsumerRecord` or manually constructing a `ProducerRecord`. It should be distinguished from Kafka serializer/deserializer: serializers and deserializers are responsible for converting keys/values between objects and bytes; the message converter is responsible for conversion at the record and Spring Message layer.

## 1. Where does MessagingMessageConverter sit?

A Kafka pipeline has two separate conversion boundaries:

- **Serialization:** The Kafka producer converts key/value to bytes; the consumer converts bytes back into a Java data type.
- **Message conversion:** Spring Kafka converts a record into a Spring `Message<?>` or converts a Spring Message into a Kafka record.

`MessagingMessageConverter` implements `RecordMessageConverter`. It works with the entire record and headers, and does not replace the Kafka client's `Serializer` or `Deserializer`.

```mermaid
flowchart LR
    subgraph Producer
      A[Spring Message] --> B[MessagingMessageConverter]
      B --> C[ProducerRecord]
      C --> D[Kafka Serializer]
      D --> E[Kafka bytes]
    end
    subgraph Consumer
      F[Kafka bytes] --> G[Kafka Deserializer]
      G --> H[ConsumerRecord]
      H --> I[MessagingMessageConverter]
      I --> J[Spring Message]
      J --> K[@KafkaListener]
    end
```

For example: `JsonSerializer` converts `OrderCreated` into JSON bytes. When the consumer uses `JsonDeserializer`, the payload of the `ConsumerRecord` is already `OrderCreated`; `MessagingMessageConverter` further wraps the payload and metadata into a `Message<OrderCreated>` for the listener to receive.

## 2. Distinguishing the conversion components

| Component | Input | Output | Responsibility |
|---|---|---|---|
| Kafka `Serializer` | Java key/value | `byte[]` | Encodes data for transmission over the Kafka protocol |
| Kafka `Deserializer` | `byte[]` | Java key/value | Decodes data received from Kafka |
| `RecordMessageConverter` | `ConsumerRecord` or Spring `Message<?>` | Spring `Message<?>` or `ProducerRecord` | Converts full Kafka records and messages |
| `MessagingMessageConverter` | Kafka record or Spring Message | Spring Message or Kafka record | Implements record conversion, including payload and header mapping |
| `SmartMessageConverter` | Payload inside Spring Message | Payload of target type or converted message | Converts payload at the Spring Messaging layer when configured |
| `HeaderMapper` | Kafka headers or Spring headers | Spring headers or Kafka headers | Maps metadata between the two header systems |

A common design mistake is thinking `MessagingMessageConverter` automatically turns JSON bytes into a POJO in every case. Decoding bytes belongs first to the Kafka deserializer. If the deserializer returns a `String`, the record converter can wrap that string into a Message; to convert the JSON string into a POJO, you need to add a suitable payload converter or use `JsonDeserializer` directly at the Kafka layer.

## 3. Converting ConsumerRecord to Spring Message

On the inbound side, the converter takes the `ConsumerRecord` returned by the Kafka consumer and creates a Spring Message. The payload is typically taken from `record.value()` after the Kafka deserializer has processed it. Metadata such as topic, partition, offset, timestamp, and key are placed into message headers.

Example listener receiving `Message<OrderCreated>`:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @KafkaListener(topics = "orders.created.v1", groupId = "order-projection")
    public void onOrder(Message<OrderCreated> message) {
        OrderCreated event = message.getPayload();

        String topic = message.getHeaders()
                .get(KafkaHeaders.RECEIVED_TOPIC, String.class);
        Integer partition = message.getHeaders()
                .get(KafkaHeaders.RECEIVED_PARTITION, Integer.class);
        Long offset = message.getHeaders()
                .get(KafkaHeaders.OFFSET, Long.class);

        // Process event and metadata needed for tracing.
    }
}
```

Commonly used inbound headers include:

| Spring Kafka Header | Meaning |
|---|---|
| `KafkaHeaders.RECEIVED_TOPIC` | Topic from which the record was received |
| `KafkaHeaders.RECEIVED_PARTITION` | Partition of the record |
| `KafkaHeaders.OFFSET` | Offset of the record within the partition |
| `KafkaHeaders.RECEIVED_KEY` | Deserialized key of the record |
| `KafkaHeaders.RECEIVED_TIMESTAMP` | Timestamp received from the record |
| `KafkaHeaders.TIMESTAMP_TYPE` | Timestamp type of the record |
| `KafkaHeaders.GROUP_ID` | Consumer group associated with the listener |

Additional headers such as acknowledgment or consumer may be added to the Message depending on listener configuration and context. Only read the headers you need; do not pass the entire consumer or acknowledgment object across multiple business layers without a clear reason.

## 4. Receiving payload and metadata with @Payload, @Header

If the method only needs a few fields, you can declare the payload and headers as separate parameters instead of accepting the entire `Message<?>`:

```java
@KafkaListener(topics = "orders.created.v1", groupId = "order-projection")
public void onOrder(
        @Payload OrderCreated event,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset) {

    // Process event with Kafka coordinates.
}
```

Spring Kafka supports resolving payloads and headers from the message created by the listener adapter. This approach is concise when the listener only needs a few metadata fields.

Choose how to accept parameters based on your needs:

- `OrderCreated`: only business data is needed.
- `Message<OrderCreated>`: multiple message headers are needed or you want to forward the message envelope to another component.
- `ConsumerRecord<String, OrderCreated>`: raw Kafka API, Kafka headers, or full record details are needed.
- `@Payload` and `@Header`: you want to explicitly declare each value used by the listener.

You do not always need `MessagingMessageConverter` just to read a POJO payload. If the listener receives the payload directly and does not need Spring Message headers, a normal parameter type can meet the requirement.

## 5. Converting Spring Message to ProducerRecord

On the outbound side, `MessagingMessageConverter` reads the payload and control headers for sending the record to build a `ProducerRecord`. Important headers may include topic, partition, key, and timestamp.

Example building a message:

```java
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

OrderCreated event = new OrderCreated("evt-1001", "order-42");

Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, "orders.created.v1")
        .setHeader(KafkaHeaders.MESSAGE_KEY, event.orderId())
        .setHeader("event-source", "order-service")
        .build();
```

Then send using `KafkaTemplate.send(Message<?>)`:

```java
kafkaTemplate.send(message)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                // Handle publish failure.
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();
            // Record topic, partition, and offset.
        });
```

`KafkaHeaders.TOPIC` specifies the target topic. `KafkaHeaders.MESSAGE_KEY` supplies the key for the record. You can also pass `KafkaHeaders.PARTITION` or `KafkaHeaders.TIMESTAMP` when you need to specify a partition or timestamp. If partition is not specified, the Kafka partitioner chooses a partition based on the key and producer configuration.

`send(Message<?>)` uses `KafkaTemplate`'s message converter to construct the record. The Kafka producer still requires a serializer compatible with the key/value types after conversion.

## 6. Configuring MessagingMessageConverter for the listener container

You can attach `MessagingMessageConverter` to `ConcurrentKafkaListenerContainerFactory` using `setRecordMessageConverter`:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            ordersListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setRecordMessageConverter(new MessagingMessageConverter());
        return factory;
    }
}
```

Listener selecting this factory:

```java
@KafkaListener(
        topics = "orders.created.v1",
        groupId = "order-projection",
        containerFactory = "ordersListenerContainerFactory"
)
public void onOrder(Message<OrderCreated> message) {
    // Payload and headers have been converted into a Spring Message.
}
```

The factory can be shared across multiple listeners. If listeners receive `ConsumerRecord` or the payload directly without needing Spring Message, consider whether a custom record converter is truly needed.

## 7. Configuring the converter for KafkaTemplate

`KafkaTemplate` can also use a `RecordMessageConverter` to support the Spring Message send API:

```java
@Configuration
public class KafkaProducerConfiguration {

    @Bean
    public KafkaTemplate<String, OrderCreated> orderKafkaTemplate(
            ProducerFactory<String, OrderCreated> producerFactory) {

        var template = new KafkaTemplate<>(producerFactory);
        template.setMessageConverter(new MessagingMessageConverter());
        return template;
    }
}
```

Then you can call:

```java
Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, "orders.created.v1")
        .setHeader(KafkaHeaders.MESSAGE_KEY, event.orderId())
        .build();

orderKafkaTemplate.send(message);
```

If the application uses Spring Boot auto-configuration, you can configure `KafkaTemplate` via a custom bean or configuration matching the version in use. When creating the template manually, ensure the `ProducerFactory` has key/value serializers matching the record types being sent.

## 8. HeaderMapper and header mapping

Kafka headers and Spring `MessageHeaders` do not share the same data types. A Kafka header is a pair of name and byte array; a Spring Message header can hold Strings, numbers, objects, or other metadata types. `MessagingMessageConverter` uses `HeaderMapper` to map between the two models.

`DefaultKafkaHeaderMapper` is the common choice when mapping multiple header types. It can convert header objects into an appropriate representation and carry type metadata for headers that are not simple bytes/strings. Mapping pattern options allow restricting which headers are transferred across.

Example of some application headers:

```java
Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, "orders.created.v1")
        .setHeader(KafkaHeaders.MESSAGE_KEY, event.orderId())
        .setHeader("event-source", "order-service")
        .setHeader("correlation-id", "corr-8f31")
        .build();
```

The `event-source` and `correlation-id` headers are application metadata. `KafkaHeaders.TOPIC` and `KafkaHeaders.MESSAGE_KEY` control record creation. The converter handles headers according to their roles when building the `ProducerRecord`.

Do not place large data or unnecessarily complex objects in headers. Headers should be small, stable, and have a clear schema/type. Avoid transmitting secrets such as access tokens, passwords, or sensitive personal data in headers.

## 9. Customizing HeaderMapper

When you only want to propagate a specific set of headers, you can configure a mapper explicitly and attach it to `MessagingMessageConverter`:

```java
@Bean
public RecordMessageConverter orderRecordMessageConverter() {
    var headerMapper = new DefaultKafkaHeaderMapper();
    var converter = new MessagingMessageConverter(headerMapper);
    return converter;
}
```

Then attach the converter to the listener factory or `KafkaTemplate` as in the earlier examples.

In systems with security requirements or multi-language interoperability, configure header mapping using an appropriate allowlist/pattern instead of forwarding arbitrary headers. Constructor names and pattern configuration methods on the mapper may differ by Spring Kafka version; check the API you are using before adding filters.

A header mapper only maps metadata. It neither authenticates the sender nor guarantees that header values are valid for business logic. The consumer must still validate incoming data.

## 10. Using SmartMessageConverter to convert payloads

`MessagingMessageConverter` focuses on converting between records and Spring Messages. When you need to convert a payload from one type to another, you can attach a Spring Messaging `SmartMessageConverter` via `setMessagingConverter(...)`.

For example, if the consumer uses `StringDeserializer` and receives JSON as a string, a Spring JSON converter can convert the string payload into a DTO when the listener declares the corresponding target type. You need to set the content type or configure the converter appropriately so it knows how to interpret the payload.

Concept:

```text
Kafka bytes
   |
StringDeserializer
   v
String JSON
   |
MessagingMessageConverter
   v
Spring Message<String>
   |
SmartMessageConverter (if configured)
   v
Spring Message<OrderCreated>
```

Illustrative configuration example:

```java
var recordConverter = new MessagingMessageConverter();
recordConverter.setMessagingConverter(new MappingJackson2MessageConverter());
```

`MappingJackson2MessageConverter` belongs to Spring Messaging and must be configured properly for the application's content type/target type. API names and target type support depend on the Spring Framework version. Test with real payloads rather than assuming every JSON string converts automatically.

If the consumer already uses Kafka's `JsonDeserializer` to produce `OrderCreated`, you typically do not need to add another JSON message converter to deserialize again. Choose one layer responsible for converting JSON into objects to avoid duplicate conversion or type conflicts.

## 11. Choosing a clear JSON strategy

Two common implementation approaches:

| Strategy | Consumer deserializer | Payload after deserializer | Role of message converter |
|---|---|---|---|
| JSON at the Kafka layer | `JsonDeserializer<OrderCreated>` | `OrderCreated` | Wraps record into Spring Message and maps headers |
| JSON at the Spring Messaging layer | `StringDeserializer` | `String` | Can use `SmartMessageConverter` to convert JSON String to DTO |

### Strategy A: Kafka JsonDeserializer

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.acme.orders.events.OrderCreated
        spring.json.use.type.headers: false
        spring.json.trusted.packages: com.acme.orders.events
```

The listener receives `OrderCreated` or `Message<OrderCreated>`. The message converter handles the envelope and header mapping.

### Strategy B: StringDeserializer and payload conversion

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
```

The record converter receives a String payload; a suitable `SmartMessageConverter` can convert the payload to the type required by the listener if content type and target type are supplied correctly. This approach is useful when the application wants to control conversion at the Spring Messaging layer or needs to handle multiple payload formats.

Do not configure `JsonDeserializer` and at the same time expect `SmartMessageConverter` to reprocess the original JSON bytes. When using `JsonDeserializer`, the upper converter receives an already-deserialized object, no longer the raw JSON bytes.

## 12. Handling null payloads and tombstones

In Kafka, a record with a `null` value is commonly used as a tombstone in a compacted topic. This is a record with a key but no value, signifying deletion of the key from compacted state once compaction occurs.

Spring Kafka provides `KafkaNull` to represent null payloads in certain message APIs. If a listener receives tombstones, design the handler method for a nullable payload type or accept `ConsumerRecord` to check `value() == null`.

Example:

```java
@KafkaListener(topics = "customer-state", groupId = "customer-projection")
public void onCustomerRecord(ConsumerRecord<String, CustomerState> record) {
    if (record.value() == null) {
        // Handle tombstone: delete state by key.
        return;
    }

    // Update customer state.
}
```

Do not treat every null payload as a malformed message. In a compacted topic, a tombstone can be a valid part of the data contract. Agree on null semantics between producer and consumer.

## 13. Batch listeners and batch message conversion

`MessagingMessageConverter` is a per-record converter. When a listener receives in batch mode, Spring Kafka uses the `BatchMessageConverter` mechanism, typically `BatchMessagingMessageConverter`, to convert a list of `ConsumerRecord`s into a batch message.

Example of a listener receiving a payload list:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-batch",
        containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(List<OrderCreated> events) {
    // Process batch of records.
}
```

The factory must be configured with batch listener mode and an appropriate batch message converter. Do not attach a per-record `MessagingMessageConverter` and assume it automatically turns the whole batch into `List<Message<?>>`; use `BatchMessageConverter` for the batch contract.

When a batch listener needs per-record metadata, it can accept a list of `ConsumerRecord`s or the batch message structure per the Spring Kafka API. Design partial-batch error handling and offset commits accordingly.

## 14. Common pitfalls when using MessagingMessageConverter

**Confusing converter with deserializer:** the converter receives the record after the Kafka deserializer has processed key/value. Check `key-deserializer` and `value-deserializer` first.

**Payload does not match listener's expected type:** the deserializer returns `String` while the listener expects a POJO. Use `JsonDeserializer` or configure a `SmartMessageConverter` with the right target type.

**KafkaTemplate sends a message without a topic header:** `send(Message<?>)` needs to know the topic from `KafkaHeaders.TOPIC` or a properly configured default topic.

**Serializer incompatible with payload:** the converter builds a `ProducerRecord` containing a POJO while the producer factory uses `StringSerializer`. Choose a matching serializer or convert the payload to a type the serializer supports.

**Headers do not appear at the consumer:** check `HeaderMapper`, mapping patterns, and header names. Not every Spring header automatically becomes a Kafka header.

**Putting Kafka metadata into the wrong headers:** use `KafkaHeaders.MESSAGE_KEY`, `KafkaHeaders.PARTITION`, `KafkaHeaders.TIMESTAMP`, and `KafkaHeaders.TOPIC` according to their outbound purpose.

**Running JSON conversion twice:** `JsonDeserializer` already built a POJO, yet `SmartMessageConverter` tries to convert the payload as a string. Pick one layer to deserialize JSON.

**Using a record converter for a batch listener:** a batch listener requires the corresponding `BatchMessageConverter`.

**Treating tombstones as ordinary payloads:** check for null values and compacted topic contracts.

**Incompatible header objects across services:** standardize header types, use a controlled mapper, and avoid passing internal Java objects as inter-service contracts.

## 15. Testing message conversion

Test both inbound and outbound directions separately:

- **Outbound:** a Spring Message with proper topic/key/headers converts into the expected ProducerRecord.
- **Inbound:** a ConsumerRecord with payload and Kafka headers converts into a Spring Message with the right payload/headers.
- **Payload conversion:** JSON String converts to POJO only when SmartMessageConverter and target type are properly configured.
- **Header mapping:** allowed headers pass through the mapper; disallowed headers are not propagated unintentionally.
- **Serializer/deserializer:** data types before and after the record converter are compatible with the Kafka client.
- **Tombstones:** null payloads are handled according to contract.
- **Batch:** use a batch converter and verify per-record metadata if needed.

For example, integration tests should use `@EmbeddedKafka` or Testcontainers to verify the full path: `KafkaTemplate` sends a message, the broker stores the record, the consumer deserializes, the converter builds the message, and the listener receives the payload. Unit tests can mock `KafkaTemplate` or test the converter directly, but they do not prove that serializers/deserializers and the broker work together.

Do not only assert that the listener was invoked. Verify topic, key, payload, and important headers. If `KafkaHeaders.OFFSET` or partition is used in processing, verify they come from the actual record.

## 16. Implementation checklist

- Distinguished Kafka serializer/deserializer from `RecordMessageConverter`.
- Determined whether the listener needs direct payload, `Message<?>`, or `ConsumerRecord`.
- Listener factory uses the right `RecordMessageConverter` when Spring Message conversion is needed.
- `KafkaTemplate` uses an appropriate converter when sending `Message<?>`.
- `KafkaHeaders.TOPIC` and key/partition/timestamp are properly set on outbound messages.
- `HeaderMapper` only propagates necessary headers and has a clear contract.
- `SmartMessageConverter` is added only when payload conversion between types is genuinely needed.
- JSON is deserialized at a single chosen layer and serializer/deserializer match.
- Batch listeners use `BatchMessageConverter`.
- Tombstone/null payloads have clear handling semantics.
- Integration tests cover inbound, outbound, header mapping, and payload conversion.
- Logs/traces record only necessary metadata, without logging secrets or sensitive payloads.

`MessagingMessageConverter` connects Kafka records to Spring's `Message<?>` model. By keeping clear boundaries between serializer/deserializer, record converter, payload converter, and header mapper, applications can exchange events with Spring Messaging consistently while maintaining control over data types, metadata, and listener behavior.

# When to use a converter instead of a serializer

In Spring Kafka, both serializers and message converters can participate in data transformation, but they operate at two different layers. **Kafka `Serializer`/`Deserializer` is responsible for turning keys/values into bytes and reading bytes back. Spring `RecordMessageConverter` converts between Kafka records and Spring `Message<?>`, and can also convert payloads to the type requested by the listener.**

Therefore, the question is not about choosing one component to completely replace the other. A Kafka producer still needs a serializer to write bytes to the broker, and a consumer still needs a deserializer to read bytes. A converter should only be added when the application needs conversion capabilities at the Spring Messaging layer, such as working with `Message<?>`, mapping headers, `Content-Type`, or converting a JSON string into a DTO.

## 1. Two different conversion layers

Outbound flow when sending a Spring `Message<?>`:

```text
Spring Message<OrderCreatedEvent>
          |
          v
RecordMessageConverter
          |
          v
ProducerRecord<String, String>
          |
          v
StringSerializer
          |
          v
Kafka bytes
```

Inbound flow when using a JSON message converter:

```text
Kafka bytes
    |
    v
StringDeserializer
    |
    v
ConsumerRecord<String, String>
    |
    v
StringJacksonJsonMessageConverter
    |
    v
Spring Message<OrderCreatedEvent>
    |
    v
@KafkaListener
```

Here, serializers/deserializers operate at the Kafka protocol boundary. The converter runs after the Kafka client has created a `ProducerRecord` or `ConsumerRecord`, and can map payloads along with metadata to Spring's abstraction.

If using `JsonSerializer`/`JsonDeserializer`, the flow is simpler:

```text
Producer DTO -> JsonSerializer -> Kafka bytes
Kafka bytes -> JsonDeserializer -> Consumer DTO
```

The listener can receive the DTO directly without a JSON message converter. The default converter can still be used by the listener adapter to map records and headers when the method accepts `Message<T>`.

## 2. Quick comparison table

| Criterion | Kafka Serializer/Deserializer | Spring RecordMessageConverter |
| --- | --- | --- |
| Operating layer | Kafka client, byte boundary | Spring Messaging, between Kafka record and Spring message |
| Input/output | Java key/value ↔ `byte[]` | `ConsumerRecord` ↔ `Message<?>`; `Message<?>` ↔ `ProducerRecord` |
| Is it required? | Yes, producer/consumer must have a serialization/deserialization mechanism | Optional; used when conversion is needed at the Spring layer |
| Scope | Every Kafka client, including non-Spring applications | Spring Kafka applications |
| Data contract | Defines the actual byte format written to Kafka | Defines how Spring represents payloads and metadata |
| Examples | `StringSerializer`, `JsonSerializer`, Avro/Protobuf serializer | `MessagingMessageConverter`, `StringJacksonJsonMessageConverter` |
| Metadata | Typically focuses on key/value; Kafka headers are managed separately | Maps Spring `MessageHeaders` and Kafka headers |

A converter can turn a DTO into a JSON `String`, but Kafka still needs `StringSerializer` to convert that string into bytes. Likewise, an inbound converter can turn a JSON string into a DTO, but the Kafka consumer beforehand still needs `StringDeserializer` to produce a string from bytes.

## 3. When should you use serializer/deserializer directly?

Prefer serializers/deserializers when the byte format is the system's primary contract and the application does not need extra conversion at the Spring Messaging layer.

Common scenarios:

- Producer sends a DTO and consumer receives the same DTO type using `JsonSerializer`/`JsonDeserializer`.
- Multiple applications written in Java, Go, Python, or .NET need to share a single wire format.
- The system uses Avro, Protobuf, or a schema registry to manage schemas and compatibility.
- Payloads are `String`, `byte[]`, or simple types that already have matching serializers.
- The application only needs the payload parameter in `@KafkaListener`, without `Message<?>` or custom header mapping.
- You want serialization/deserialization errors to surface cleanly at the Kafka client boundary and be handled by the Kafka serializer/deserializer or corresponding error handler.

Example direct JSON configuration:

```yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.value.default.type]": com.example.events.OrderCreatedEvent
        "[spring.json.trusted.packages]": com.example.events
```

Producer sending an object directly:

```java
KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

public void publish(OrderCreatedEvent event) {
    kafkaTemplate.send("orders.created", event.orderId(), event);
}
```

Consumer receiving DTO:

```java
@KafkaListener(topics = "orders.created", groupId = "order-projection")
public void onMessage(OrderCreatedEvent event) {
    // Process DTO created by JsonDeserializer.
}
```

In this example, `JsonSerializer` is responsible for producing JSON bytes and `JsonDeserializer` is responsible for creating the DTO. Adding another JSON message converter usually only increases conversion steps and the risk of duplicate parsing/serialization.

## 4. When should you use RecordMessageConverter?

Use a converter when the application needs a conversion layer tied to Spring Messaging or needs to adapt payloads based on listener context.

**Case 1: Application uses Spring `Message<?>`.**

Services already build messages using `MessageBuilder`, carrying payloads and headers such as topic, key, correlation ID, or content type. `KafkaTemplate.send(Message<?>)` uses the converter to turn that message into a `ProducerRecord`.

**Case 2: Kafka payload is String or bytes, but the listener needs a DTO.**

Producer/consumer use simple serializers/deserializers, such as `StringSerializer`/`StringDeserializer`. A JSON converter turns objects into strings when sending and turns strings into DTOs when receiving.

**Case 3: Metadata and header mapping are needed.**

The listener needs `Message<T>` containing payload along with topic, partition, offset, key, correlation ID, or business headers. `MessagingMessageConverter` and header mappers provide this mapping layer.

**Case 4: Conversion depends on Content-Type or listener parameter type.**

The application receives multiple payload types, using `SmartMessageConverter` or a JSON converter to choose conversion behavior from media type and the listener method's target type.

**Case 5: Integrating with existing Spring Messaging APIs.**

If components within the application already exchange `Message<?>`, the converter connects Kafka to that message model without forcing services to manipulate `ProducerRecord` and `ConsumerRecord` directly.

## 5. Example: same DTO, two configuration approaches

Suppose the application exchanges an event:

```java
public record OrderCreatedEvent(
        String eventId,
        String orderId,
        BigDecimal total) {
}
```

### Approach A — JSON serializer/deserializer

```yaml
spring:
  kafka:
    producer:
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.value.default.type]": com.example.events.OrderCreatedEvent
        "[spring.json.trusted.packages]": com.example.events
```

The producer sends `OrderCreatedEvent`; the consumer receives `OrderCreatedEvent`. This is a concise option when JSON payload is the contract and the listener only needs the DTO.

### Approach B — String serializer/deserializer and JSON message converter

```yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
```

With Spring Kafka 4.x, create the converter:

```java
@Bean
RecordMessageConverter recordMessageConverter() {
    return new StringJacksonJsonMessageConverter();
}
```

Attach the converter to the listener container factory:

```java
factory.setRecordMessageConverter(recordMessageConverter);
```

Attach the converter to `KafkaTemplate` if sending Spring `Message<?>`:

```java
kafkaTemplate.setMessageConverter(recordMessageConverter);
```

Now the producer can send an object inside a Spring message:

```java
Message<OrderCreatedEvent> message = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, "orders.created")
        .setHeader(KafkaHeaders.KEY, event.orderId())
        .build();

kafkaTemplate.send(message);
```

The converter turns the DTO payload into a JSON string; `StringSerializer` turns the string into bytes. On the receiving side, `StringDeserializer` produces a string; the converter turns the string into a DTO based on the type requested by the listener.

Converter names depend on the version: Spring Kafka 4.x uses `StringJacksonJsonMessageConverter` (Jackson 3); Spring Kafka 3.x and earlier use `StringJsonMessageConverter` (Jackson 2). Do not mix converter classes from the two Jackson generations.

## 6. When to combine both serializer and converter?

In most Spring Kafka applications, both layers coexist. A configuration might use:

- `StringSerializer` to write keys.
- `StringSerializer` or `JsonSerializer` to write values.
- `StringDeserializer` or `JsonDeserializer` to read values.
- Default `MessagingMessageConverter` to map Kafka records into Spring `Message<?>`.
- JSON `RecordMessageConverter` if the payload remains String/bytes while Spring listeners need DTOs.

For example, an application uses an Avro serializer to produce Avro bytes. Once the consumer uses an Avro deserializer to produce `OrderCreatedEvent`, the default converter can wrap that object along with metadata into `Message<OrderCreatedEvent>`. A JSON converter does not need to participate.

A helpful rule: **serializer/deserializer determines bytes on Kafka; converter determines how the Spring adapter represents and transforms payloads/metadata for the application.**

## 7. Which APIs actually trigger the message converter?

Not every method on `KafkaTemplate` uses the converter.

| API | Is the converter invoked? | Notes |
| --- | --- | --- |
| `KafkaTemplate.send(topic, key, value)` | No | Key/value go straight through the Kafka serializer |
| `KafkaTemplate.send(ProducerRecord)` | No | `ProducerRecord` is already created; producer serializer handles bytes |
| `KafkaTemplate.send(Message<?>)` | Yes | Template converts Spring Message into `ProducerRecord` |
| Listener receiving payload via container | Has record-to-message step | Container uses `RecordMessageConverter`; custom converter can transform payload |
| Listener receiving `ConsumerRecord<K,V>` | No payload conversion needed for record parameter | Application receives the Kafka record directly |

Therefore, if you configured a converter but call `send(topic, key, value)`, do not expect the converter to turn a DTO into JSON automatically. Use a matching serializer or send `Message<?>` through the converter-aware overload.

## 8. Trade-offs when adding a converter

A converter adds integration flexibility, but also adds another layer of configuration and transformation.

| Aspect | Benefit | Cost/risk |
| --- | --- | --- |
| Spring Messaging | Consistent use of `Message<?>` and headers | Coupling to Spring Kafka abstractions and APIs |
| Payload conversion | Converts String/bytes to DTO per listener | CPU cost, object allocation, and potential extra JSON parse |
| Header mapping | Propagates correlation ID, content type, and metadata | Requires managing allowlist, encoding, and header types |
| Multiple payload types | Can select converter by content type/target type | Complex configuration, type resolution errors harder to trace |
| System compatibility | Can keep simple wire formats like String/bytes | Must align converter and serializer across all producers/consumers |

For large payloads or high throughput, measure CPU, allocation, and latency before adding another conversion step. If you only need JSON DTOs, `JsonSerializer`/`JsonDeserializer` is usually simpler.

## 9. Choosing by data type and architecture

| Scenario | Recommendation |
| --- | --- |
| Single JSON topic, Spring producer/consumer sharing DTO | `JsonSerializer`/`JsonDeserializer` |
| JSON topic consumed by multiple languages | Choose a stable JSON wire format; per-language serializers/deserializers are usually the main boundary |
| Service already uses `Message<?>` and needs header mapping | `RecordMessageConverter` |
| Kafka value is JSON String, but listeners need different DTOs | JSON message converter or `SmartMessageConverter` by target type/content type |
| Avro/Protobuf with schema registry | Dedicated serializer/deserializer; add converter only if Spring Message abstraction is needed |
| Raw bytes, file chunks, or binary protocol | Byte-array serializer/deserializer; converter only if metadata wrapping is needed |
| Listener needs `topic`, `partition`, `offset`, `key` | `Message<T>` with default converter or `ConsumerRecord<K,V>` |
| Only sending DTOs via `KafkaTemplate.send(topic,key,value)` | Direct serializer |

Do not pick a converter simply because its name sounds more general. Choose it when you need Spring Messaging-layer capabilities that serializers/deserializers do not address.

## 10. Things a converter does not replace for a serializer

A converter does not change the fundamental requirements of Kafka producers/consumers:

- The producer must still have serializers for key/value.
- The consumer must still have deserializers for key/value.
- The converter does not configure partitioner, compression, `acks`, retries, or transactions.
- The converter does not replace a schema registry or automatically guarantee schema compatibility.
- The converter does not turn Kafka headers into storage for large payloads or secrets.
- The converter does not guarantee exactly-once semantics or business idempotency.

If the serializer/deserializer does not match the data type produced by the converter, errors still occur in the Kafka client. For example, the converter produces `String` while the producer factory uses a serializer that only accepts a different DTO type.

## 11. Testing when choosing a converter

When adding a converter, test both the conversion step and the real send/receive path.

1. **Converter unit tests:** test converting DTO payloads to String/bytes and back; verify null, malformed payloads, and type mismatches.
2. **Header mapping tests:** verify topic, key, partition, timestamp, correlation ID, and custom headers are mapped accurately.
3. **Template tests:** verify `send(Message<?>)` goes through the converter and produces the right `ProducerRecord`; also confirm `send(topic,key,value)` uses the serializer directly.
4. **Listener integration tests:** send records through a test broker and verify the final payload type received by the listener.
5. **Compatibility tests:** use payloads generated by producers in another language or version to verify the wire contract.

With a JSON converter, test both with and without `Content-Type` from the producer, invalid type headers, new fields, and legacy payloads. If the converter uses Jackson, test date/time modules and unknown-properties policies per the event contract.

## 12. Common pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Configured converter, yet `send(topic,key,value)` still fails serialization | That API does not invoke the message converter | Use a matching serializer or `send(Message<?>)` |
| Listener receives String instead of DTO | Deserializer returns String and no JSON converter is configured | Configure JSON `RecordMessageConverter` or use `JsonDeserializer` |
| JSON converted twice | Using both `JsonDeserializer` to build DTO and a JSON converter to parse again | Assign JSON payload handling to one layer |
| Outbound `Message<?>` lacks topic | Missing `KafkaHeaders.TOPIC` and default topic | Set topic header or default topic |
| Custom headers lost | Header mapper does not map header or encoding is wrong | Configure mapper and test each header |
| Producer and consumer disagree on value type | Converter outputs String while serializer/deserializer uses another type | Align generic types and Kafka client configuration |
| Using Jackson 2 converters on Spring Kafka 4.x | Mismatched converter/dependency generation | Use matching Jackson 3 classes or keep Spring Kafka 3.x stack aligned |

## 13. Conclusion

Use Kafka serializers/deserializers to define how keys/values are written as bytes and read back from Kafka. Use Spring `RecordMessageConverter` when you need to convert Kafka records into Spring `Message<?>`, map headers, convert JSON strings/bytes into DTOs per listener type, or integrate with Spring Messaging APIs.

If producer and consumer simply exchange JSON DTOs, `JsonSerializer`/`JsonDeserializer` is usually the direct option with less configuration. If the application needs `Message<?>`, content types, header mapping, or wants to keep the Kafka client on String/bytes and convert payloads at the Spring layer, converters deliver clear value. In both cases, serializers/deserializers remain ultimately responsible at Kafka's byte boundary.

## References

- [Spring for Apache Kafka — Message Conversion](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html)
- [Spring for Apache Kafka — Serialization, Deserialization and Message Conversion](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html#serdes-json-config)
- [Spring for Apache Kafka — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
- [Apache Kafka — Serializer API](https://kafka.apache.org/documentation/#producerapi)

# Mapping between Kafka records and Spring Message

Spring Kafka bridges two different message models. The Kafka client works with records containing key, value, topic, partition, offset, timestamp, and byte-based headers. Spring Messaging represents a message using a payload along with a set of MessageHeaders. Message conversion is the bridge layer that enables applications to use `@KafkaListener`, `KafkaTemplate`, `@Payload`, and `@Header` in a way that is consistent with the Spring ecosystem.

Message conversion must be distinguished from serialization/deserialization. Serializers and deserializers convert data between objects and bytes when exchanging messages with the broker. A message converter converts between a Kafka ProducerRecord/ConsumerRecord and a Spring `Message<?>`; the converter can also perform payload conversion, such as converting a JSON String into a Java object. These two layers collaborate but solve different responsibilities.

In a Spring Kafka application, you can receive a `ConsumerRecord` directly when full access to Kafka metadata is needed, or receive a `Message<T>` when you want to work with payload and headers following the Spring model. On the outbound side, `KafkaTemplate.send(Message<?>)` allows creating a `ProducerRecord` from the payload and headers of a Spring Message.

## Learning Objectives

After this lesson, you will be able to:

- Describe the structure of a Kafka record and a Spring `Message<?>`.
- Distinguish between serializer/deserializer and `RecordMessageConverter`.
- Explain how `MessagingMessageConverter` maps payloads and headers between the two models.
- Read topic, partition, offset, key, and timestamp from Spring Message headers.
- Use `@Payload`, `@Header`, and `@Headers` in `@KafkaListener`.
- Send messages using `KafkaTemplate.send(Message<?>)` with topic, key, and custom headers.
- Choose a default converter or a JSON message converter compatible with the serializer/deserializer.
- Configure converters for the listener container factory and `KafkaTemplate`.
- Understand how batch messages, native Kafka headers, and conversion errors are handled.
- Test mappings and avoid losing metadata or performing payload conversion twice.

## 1. The two message models

The Kafka client works with records. A `ConsumerRecord` contains information such as:

- topic: the name of the topic containing the record.
- partition: the partition containing the record.
- offset: the position of the record within the partition.
- key: the key after conversion by the deserializer.
- value: the payload after conversion by the deserializer.
- timestamp: the record timestamp according to the timestamp type.
- headers: the collection of Kafka Headers, each having a name and a byte value.

Spring Messaging uses the `Message<T>` interface, consisting of:

- payload: the main content of the message.
- headers: `MessageHeaders`, a read-only map containing metadata and custom headers.

Diagram:

~~~text
Kafka ConsumerRecord / ProducerRecord
  topic, partition, offset, key, value, timestamp, Kafka Headers
                       |
                       | RecordMessageConverter
                       v
Spring Message<T>
  payload + MessageHeaders
~~~

Example of the same order event:

~~~text
Kafka record:
  topic     = orders
  partition = 2
  offset    = 105
  key       = order-100
  value     = OrderCreated(...)
  headers   = trace-id, event-source

Spring Message:
  payload = OrderCreated(...)
  headers = received topic, partition, offset, key,
            timestamp, trace-id, event-source
~~~

A Spring Message is not a new Kafka record. It is an application-layer representation of the message, created from a record or used as input to create an outbound record.

## 2. Distinguishing serialization and message conversion

This is the most important boundary when configuring Spring Kafka.

| Layer | Input | Output | Commonly used components |
|---|---|---|---|
| Serialization | Java key/value | byte[] | Serializer |
| Deserialization | byte[] | Java key/value | Deserializer |
| Inbound message conversion | ConsumerRecord | Spring Message<?> or payload per method signature | RecordMessageConverter |
| Outbound message conversion | Spring Message<?> | ProducerRecord | RecordMessageConverter |
| JSON payload conversion | JSON String/byte[] and target Java type | Java object or JSON | StringJsonMessageConverter, ByteArrayJsonMessageConverter... |

Inbound flow when using `JsonDeserializer`:

~~~text
Kafka bytes
    |
    v
JsonDeserializer
    |
    v
OrderCreated object
    |
    v
MessagingMessageConverter
    |
    v
Message<OrderCreated>
    |
    v
@KafkaListener
~~~

Inbound flow when using `StringJsonMessageConverter`:

~~~text
Kafka bytes
    |
    v
StringDeserializer
    |
    v
JSON String
    |
    v
StringJsonMessageConverter
    |
    v
OrderCreated object / Message<OrderCreated>
    |
    v
@KafkaListener
~~~

These two approaches are different options. If `JsonDeserializer` already produces `OrderCreated`, there is no need to add `StringJsonMessageConverter` to parse JSON again. Conversely, if `StringJsonMessageConverter` is used, the key/value deserializer typically returns `String` or `byte[]` for the converter to process JSON.

A message converter does not replace the Kafka client's serializer/deserializer. The broker still stores bytes; converting bytes to objects on the consumer side always requires a deserializer or a converter running after the deserializer.

## 3. RecordMessageConverter and MessagingMessageConverter

Spring Kafka defines `RecordMessageConverter` to convert between a Kafka record and a Spring Message.

Two main directions:

- `toMessage(...)`: converts a `ConsumerRecord` into a `Message<?>` for the listener.
- `fromMessage(...)`: converts a `Message<?>` into a `ProducerRecord` for sending.

`MessagingMessageConverter` is the standard implementation. It converts the payload and maps metadata/headers between the Kafka record and Spring `MessageHeaders`.

In a typical application, the listener container uses the converter to build arguments for the listener. `KafkaTemplate` uses the converter when calling the `send(Message<?>)` overload.

Common implementations and JSON variants:

| Converter | Purpose |
|---|---|
| MessagingMessageConverter | Maps Kafka record and Spring Message; payload usually keeps the type provided by serializer/deserializer |
| BatchMessagingMessageConverter | Converts a batch of ConsumerRecords into a list-based message/payload suitable for batch listeners |
| StringJsonMessageConverter | Converts between JSON String and Java object |
| ByteArrayJsonMessageConverter | Converts between JSON byte[] and Java object |
| BytesJsonMessageConverter | Converts between Kafka Bytes and Java object |

Class names and detailed APIs may vary across Spring Kafka versions. Always use a converter compatible with your application's dependency version.

## 4. Inbound conversion: ConsumerRecord to Spring Message

When a listener accepts a `Message<T>` parameter, the Spring Kafka container converts the `ConsumerRecord` into a `Message<?>` before invoking the method.

Listener example:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-service"
)
public void listen(Message<OrderCreated> message) {
    OrderCreated event = message.getPayload();

    String topic = message.getHeaders()
            .get(KafkaHeaders.RECEIVED_TOPIC, String.class);

    Integer partition = message.getHeaders()
            .get(KafkaHeaders.RECEIVED_PARTITION, Integer.class);

    Long offset = message.getHeaders()
            .get(KafkaHeaders.OFFSET, Long.class);

    orderService.process(event);
}
~~~

In the example, the payload is an `OrderCreated` already produced by the deserializer or converted by the message converter. Record location details are placed in Spring Message headers.

Commonly used Kafka headers on the inbound side:

| KafkaHeaders constant | Meaning |
|---|---|
| RECEIVED_TOPIC | Topic from which the record was received |
| RECEIVED_PARTITION | Partition from which the record was received |
| OFFSET | Offset of the record |
| RECEIVED_KEY | Deserialized key of the record |
| RECEIVED_TIMESTAMP | Timestamp of the record |
| ACKNOWLEDGMENT | Acknowledgment object if provided by the listener/container mode |
| CONSUMER | Kafka Consumer associated with receiving the record in certain listener types |

Headers may not appear in every listener type or every version/configuration. If exact metadata is needed for critical logic, verify that the header exists and use the correct data type.

### Reading metadata with @Header

It is not necessary to receive the entire `Message<?>`. You can declare the payload and individual headers separately:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-service"
)
public void listen(
        @Payload OrderCreated event,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset,
        @Header(name = KafkaHeaders.RECEIVED_KEY, required = false)
        String key) {

    log.info(
        "Received order {} from {}-{} at offset {} with key {}",
        event.orderId(), topic, partition, offset, key
    );

    orderService.process(event);
}
~~~

Use `required = false` for headers that may be absent, such as a null key. For required headers, you can let Spring throw an error if missing, but make sure the producer always sends that metadata with the record.

### Reading all Spring Message headers

You can receive the header map:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-service"
)
public void listen(
        @Payload OrderCreated event,
        @Headers Map<String, Object> headers) {

    Object traceId = headers.get("trace-id");
    Object topic = headers.get(KafkaHeaders.RECEIVED_TOPIC);

    orderService.process(event);
}
~~~

`@Headers` provides the headers that the Spring message converter populates into `MessageHeaders`. These are not the raw native Kafka Headers; if you need to read all native headers or duplicate-named headers, accept a `ConsumerRecord` and read `record.headers()`.

## 5. When should you accept Message<T> vs. ConsumerRecord?

Both parameter types are useful, depending on the listener's needs.

| Parameter type | Suitable when | Benefit |
|---|---|---|
| Direct payload, e.g. OrderCreated | Only business data is needed | Simple method, minimal dependency on metadata |
| Message<OrderCreated> | Both payload and Spring headers are needed | Easy to use @Header, MessageHeaders, and the Spring model |
| ConsumerRecord<String, OrderCreated> | Full Kafka metadata or native headers are needed | Direct access to topic, partition, offset, timestamp, key, and headers |
| List<ConsumerRecord<...>> | Batch listener needs per-record metadata | Full control over each record in the batch |

Example receiving `ConsumerRecord`:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-service"
)
public void listen(ConsumerRecord<String, OrderCreated> record) {
    log.info(
        "topic={}, partition={}, offset={}, key={}",
        record.topic(),
        record.partition(),
        record.offset(),
        record.key()
    );

    orderService.process(record.value());
}
~~~

When a method accepts `ConsumerRecord`, the application works directly with the Kafka record. There is no need to transfer metadata through Spring Message headers. This is the clear choice for logic that needs native metadata, inspects the timestamp type, or handles headers with repeated names.

Do not accept `ConsumerRecord` just to get the payload if the listener does not use metadata; a direct payload type is usually easier to read.

## 6. Outbound conversion: Spring Message to Kafka record

On the outbound side, `KafkaTemplate` supports `send(Message<?>)`. The converter reads the payload and special headers to build a `ProducerRecord`.

Example:

~~~java
@Service
public class OrderPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {

        Message<OrderCreated> message = MessageBuilder
                .withPayload(event)
                .setHeader(KafkaHeaders.TOPIC, "orders")
                .setHeader(KafkaHeaders.MESSAGE_KEY, event.orderId())
                .setHeader("trace-id", event.traceId())
                .setHeader("event-source", "checkout")
                .build();

        return kafkaTemplate.send(message);
    }
}
~~~

The example uses the Spring Kafka 3.x API, where `send()` returns a `CompletableFuture`. In Spring Kafka 2.x, the future type of the send API may be `ListenableFuture`.

Headers controlling the outbound record:

| KafkaHeaders constant | Role |
|---|---|
| TOPIC | Target topic |
| MESSAGE_KEY | Key of the record |
| PARTITION | Target partition if explicitly specified |
| TIMESTAMP | Timestamp sent with the record if supported/configured |

If `TOPIC` is absent from the message, `KafkaTemplate` needs a configured default topic to determine the destination. For readability and to avoid accidental sends to the wrong topic, either set the topic explicitly on the message or configure a default topic intentionally.

Do not set `RECEIVED_TOPIC` yourself to choose the outbound topic. Use `KafkaHeaders.TOPIC` for outbound and `KafkaHeaders.RECEIVED_TOPIC` for reading inbound metadata.

### Specifying partition and timestamp

You can specify a partition when business logic requires explicit routing:

~~~java
Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, "orders")
        .setHeader(KafkaHeaders.PARTITION, 2)
        .setHeader(KafkaHeaders.MESSAGE_KEY, event.orderId())
        .build();

kafkaTemplate.send(message);
~~~

When specifying a partition, the application is responsible for ensuring the partition exists and that this mapping aligns with ordering requirements. Normally you should let the partitioner select the partition from the key unless there is a clear reason to specify it directly.

Timestamp can be set via `KafkaHeaders.TIMESTAMP` if you need to send an application-managed timestamp. The broker/topic may use `CreateTime` or `LogAppendTime`; therefore, the received timestamp must be interpreted according to the actual timestamp type of the record.

## 7. Custom Kafka headers and header mapper

Kafka record headers store a header name and a `byte[]` value. Spring `MessageHeaders` can store Strings, numbers, objects, or other Java types. `KafkaHeaderMapper` converts between these two header models.

Diagram:

~~~text
Spring MessageHeaders
  trace-id = "trace-123"
  retry-count = 2
  event-source = "checkout"
           |
           v
      KafkaHeaderMapper
           |
           v
Kafka Headers
  trace-id      -> bytes
  retry-count   -> bytes
  event-source  -> bytes
~~~

On the inbound side, the mapper converts Kafka Headers back into values in `MessageHeaders`. The restored data types depend on the mapper, type metadata, and mapping configuration.

`DefaultKafkaHeaderMapper` supports header mapping with type conversion. `SimpleKafkaHeaderMapper` is suitable when you want to work closer to `byte[]`. Choose the mapper based on how producer/consumer systems exchange headers.

Example configuring a mapper on a converter:

~~~java
@Bean
public RecordMessageConverter recordMessageConverter() {
    MessagingMessageConverter converter =
            new MessagingMessageConverter();

    converter.setHeaderMapper(new DefaultKafkaHeaderMapper());

    return converter;
}
~~~

In multi-language systems or when producers do not use Spring, custom headers may arrive as `byte[]` instead of the original Java type. Define a clear encoding, such as UTF-8 for `trace-id`, and check the data type before casting.

### Do not blindly send all internal Spring headers

Spring `MessageHeaders` contains internal headers such as `id` and `timestamp`. Not every Spring header makes sense to a Kafka consumer. Header mappers typically have their own filtering and mapping rules; if you customize patterns, avoid accidentally leaking internal metadata or sensitive data.

Only include in Kafka the headers needed for tracing, correlation, routing, or business logic. Avoid putting tokens, credentials, personal data, or arbitrary objects into headers. Kafka headers are metadata traveling with the record and can be read by multiple consumers.

### Kafka headers can have duplicate names

Kafka Headers allow multiple headers with the same name. Spring `MessageHeaders` is a map, so a key holds only a single value. If you need to preserve all duplicate-named values or the order of native headers, read `ConsumerRecord.headers()` directly instead of relying on the converted Spring map.

## 8. JSON message conversion

When an application uses JSON, there are two common ways to convert payloads.

### Approach A: Kafka JsonSerializer and JsonDeserializer

The producer uses `JsonSerializer` to turn a Java object into `byte[]`. The consumer uses `JsonDeserializer` to reconstruct the object. The default `MessagingMessageConverter` then wraps the object along with metadata into a Spring Message.

Illustrative configuration:

~~~yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.value.default.type]": com.example.events.OrderCreated
        "[spring.json.trusted.packages]": com.example.events
~~~

Listener:

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void listen(Message<OrderCreated> message) {
    OrderCreated event = message.getPayload();
    orderService.process(event);
}
~~~

In this approach, JSON is handled by Kafka's `JsonSerializer`/`JsonDeserializer`. The message converter mainly maps the `ConsumerRecord` into a Spring Message and transfers headers.

### Approach B: StringJsonMessageConverter

The producer serializes the payload into a JSON String via the message converter; the Kafka client uses `StringSerializer` to write the String as `byte[]`. The consumer uses `StringDeserializer` to receive the String, and then `StringJsonMessageConverter` converts the JSON into the Java type requested by the listener.

Serializer/deserializer configuration:

~~~yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
~~~

Converter configuration for the listener factory:

~~~java
@Bean
public RecordMessageConverter jsonMessageConverter() {
    return new StringJsonMessageConverter();
}

@Bean
public ConcurrentKafkaListenerContainerFactory<String, String>
        orderListenerFactory(
                ConsumerFactory<String, String> consumerFactory,
                RecordMessageConverter jsonMessageConverter) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, String>();

    factory.setConsumerFactory(consumerFactory);
    factory.setRecordMessageConverter(jsonMessageConverter);

    return factory;
}
~~~

Converter configuration for `KafkaTemplate`:

~~~java
@Bean
public KafkaTemplate<String, String> orderKafkaTemplate(
        ProducerFactory<String, String> producerFactory,
        RecordMessageConverter jsonMessageConverter) {

    KafkaTemplate<String, String> template =
            new KafkaTemplate<>(producerFactory);

    template.setMessageConverter(jsonMessageConverter);

    return template;
}
~~~

Sending a Java object payload using Spring Message:

~~~java
Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, "orders")
        .setHeader(KafkaHeaders.MESSAGE_KEY, event.orderId())
        .build();

orderKafkaTemplate.send(message);
~~~

Listener receiving the object:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-service",
    containerFactory = "orderListenerFactory"
)
public void listen(OrderCreated event) {
    orderService.process(event);
}
~~~

On the outbound side, `StringJsonMessageConverter` converts the payload object into a JSON String before Kafka's `StringSerializer` runs. On the inbound side, `StringDeserializer` produces a String and then the converter turns the String into `OrderCreated` according to the listener's target type.

Do not configure `JsonDeserializer` together with `StringJsonMessageConverter` on the same value path unless you have a special design. If `JsonDeserializer` has already converted JSON into an object, `StringJsonMessageConverter` no longer has a String input to parse.

### Which approach to choose?

| Criterion | JsonSerializer/JsonDeserializer | StringJsonMessageConverter |
|---|---|---|
| JSON bytes created/parsed by | Kafka serializer/deserializer | Spring message converter combined with String serializer/deserializer |
| Listener receives object | Yes | Yes |
| Uses KafkaTemplate.send(Message<?>) | Yes, with default converter wrapping the payload object | Yes, converter turns payload into JSON String |
| Suitable when | You want serialization configured at the Kafka client level | You want conversion tied to Spring Message and listener methods |
| Interoperability with non-Spring producers | According to agreed JSON format and type metadata | According to agreed JSON String format |

What matters is that producer and consumer agree on the wire format. A non-Spring producer can send UTF-8 JSON that a consumer using `StringDeserializer` + `StringJsonMessageConverter` can read, provided the schema and payload type are compatible.

## 9. Choosing the target payload type for the listener

When using a JSON message converter, the converter needs to know the target Java type to parse JSON. Spring Kafka can infer the type from the listener parameter, for example:

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void listen(OrderCreated event) {
    orderService.process(event);
}
~~~

Or:

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void listen(Message<OrderCreated> message) {
    orderService.process(message.getPayload());
}
~~~

If the listener only accepts `Object` or an unspecified generic type, the converter may lack enough information to infer the target type. In that case, use type metadata, configure an appropriate target type, or use a listener method with a concrete type.

For a topic containing multiple event types, do not assume every record is `OrderCreated`. You can use a type header, an event type discriminator in the payload, or split topics/listeners by event type. Validate the type before invoking business logic.

## 10. Batch message conversion

When a listener container runs in batch mode, a single poll may return multiple `ConsumerRecord`s. Spring Kafka provides `BatchMessagingMessageConverter` to convert a batch into a list-shaped payload and supply per-batch metadata.

Example of a batch listener receiving a payload list:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-batch-service",
    containerFactory = "batchOrderListenerFactory"
)
public void listen(List<OrderCreated> events) {
    orderService.processBatch(events);
}
~~~

If per-record metadata is needed, you can use `List<ConsumerRecord<String, OrderCreated>>` to preserve the full original records or use the header structure designed for batch conversion such as `KafkaHeaders.BATCH_CONVERTED_HEADERS` when working with `Message<List<?>>`.

Batch conversion has several differences from a record listener:

- The payload is usually a list.
- Each record's metadata must be preserved per element, not just as a single header for the entire batch.
- A single batch can contain records from multiple partitions.
- When handling partial failures, you need to determine which records succeeded and which offsets are safe to commit.

If the application needs native headers and exact offsets for each record, receiving a list of `ConsumerRecord`s is usually easier to control.

## 11. Mapping headers and metadata in practice

Some metadata commonly used in listeners:

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void listen(
        @Payload OrderCreated event,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset,
        @Header(name = KafkaHeaders.RECEIVED_KEY, required = false)
        String key,
        @Header(name = "trace-id", required = false) String traceId) {

    log.info(
        "topic={}, partition={}, offset={}, key={}",
        topic, partition, offset, key
    );

    orderService.process(event, traceId);
}
~~~

These values are useful for logging and tracing:

- topic + partition + offset uniquely identify a record's position within a topic-partition.
- key indicates which entity the record was routed by.
- timestamp helps analyze record creation/write times.
- trace-id links producer, broker, and consumer logs.
- eventId supports business deduplication.

Do not use offset as a global event ID. An offset is unique only within a single partition; the same offset number can appear in another partition or another topic. If you need to identify a record by its Kafka position, combine topic, partition, and offset. If you need a business identifier, use `eventId`.

## 12. Which layer does an error occur in?

It is necessary to determine whether an error occurs before or after message conversion to choose the right handling strategy.

| Error layer | Example | Where typically handled |
|---|---|---|
| Deserialization | Invalid bytes, JSON unparseable by JsonDeserializer | ErrorHandlingDeserializer and listener container error handler |
| Message conversion | StringJsonMessageConverter fails to convert JSON to listener type | Listener container error handler |
| Header mapping | Header has unsupported type or malformed metadata | Header mapper/custom conversion and error handling |
| Listener method | Business exception while processing payload | CommonErrorHandler/retry/DLT as configured |
| Outbound conversion | Missing topic header or unconvertible payload | Producer call/application error handling |
| Kafka serialization | Serializer fails to convert object to bytes | Kafka producer callback/future or exception on send |

The deserializer runs before `RecordMessageConverter`. If `JsonDeserializer` fails, the converter cannot fix the payload because the `ConsumerRecord` does not yet have a valid Java value. For deserialization errors, consider `ErrorHandlingDeserializer` to turn the failure into metadata that the container error handler can process.

If the converter receives a String but the JSON is invalid, that is a message conversion error. If the converter creates the payload successfully but business logic fails, that is a listener error. Distinguishing these layers helps log and retry at the right place.

### Do not hide errors with an Object payload

Accepting an `Object` payload can allow one listener to handle multiple event types, but it also pushes type errors to surface late at runtime. If a topic has a defined schema, use concrete types or validate the event type before processing.

## 13. Raw records and tombstone/null payloads

A Kafka compacted topic can contain tombstones: records that have a key but a `null` value to represent deleting the key's state during compaction.

A standard Spring Message typically requires a non-null payload. Therefore, if a consumer must distinguish tombstones from events with a payload, accepting `ConsumerRecord` is the clear choice:

~~~java
@KafkaListener(topics = "customer-state", groupId = "customer-state-reader")
public void listen(ConsumerRecord<String, CustomerState> record) {
    if (record.value() == null) {
        customerService.deleteState(record.key());
        return;
    }

    customerService.updateState(record.key(), record.value());
}
~~~

Do not assume a standard `Message<T>` can always represent every Kafka null-value scenario. Test tombstones against the converter and listener signature you are using.

## 14. Configuring converters per listener container factory

Each listener container factory can use its own `RecordMessageConverter`. This is useful when an application has multiple topics with different wire formats.

Example of a default factory using the basic converter:

~~~java
@Bean
public RecordMessageConverter defaultRecordMessageConverter() {
    return new MessagingMessageConverter();
}
~~~

Factory using JSON String conversion:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, String>
        jsonStringListenerFactory(
                ConsumerFactory<String, String> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, String>();

    factory.setConsumerFactory(consumerFactory);
    factory.setRecordMessageConverter(new StringJsonMessageConverter());

    return factory;
}
~~~

Listener choosing the appropriate factory:

~~~java
@KafkaListener(
    id = "orders-json-listener",
    topics = "orders",
    groupId = "order-service",
    containerFactory = "jsonStringListenerFactory"
)
public void listen(OrderCreated event) {
    orderService.process(event);
}
~~~

The factory needs a `ConsumerFactory` with a matching deserializer. In the JSON String example, the value deserializer must return `String`. If using `JsonDeserializer`, choose a converter that matches the already-deserialized object.

Do not share a single converter across multiple wire formats if that converter assumes a specific payload type. Naming factories and converters after their format or domain makes configuration easier to understand.

## 15. Testing Kafka record and Spring Message mapping

Tests should verify both the payload and metadata.

Useful test scenarios:

- Send a record and receive `Message<T>`; verify the payload has the expected type.
- Verify `RECEIVED_TOPIC`, `RECEIVED_PARTITION`, `OFFSET`, `RECEIVED_KEY`, and `RECEIVED_TIMESTAMP` are mapped accurately.
- Send custom headers `trace-id` and `event-source`; verify the consumer reads the expected values and types.
- Send a `Message<?>` with `KafkaTemplate.send(Message<?>)` and verify `TOPIC`, `MESSAGE_KEY`, and `PARTITION` are applied properly.
- Use `StringJsonMessageConverter` with `StringSerializer`/`StringDeserializer` and verify JSON converts to the object.
- Use `JsonSerializer`/`JsonDeserializer` with the default `MessagingMessageConverter` and verify the payload is not parsed twice.
- Verify duplicate-named headers via `ConsumerRecord.headers()`.
- Verify a batch listener preserves per-record metadata.
- Send a tombstone/null value and verify the listener handles it correctly.
- Send malformed JSON to distinguish a deserialization error from a message conversion error.
- Test a non-Spring producer sending UTF-8 JSON and a Spring consumer reading it according to the agreed wire format.

For integration tests, use EmbeddedKafka or Testcontainers to verify real records through a broker. Converter unit tests can check local mapping, but they do not replace testing serializers/deserializers and headers on the wire.

## 16. Common pitfalls

**Confusing serializer with message converter.** `JsonSerializer` produces bytes; `MessagingMessageConverter` creates a Spring Message from a record. Choose the right layer for the job.

**Using JsonDeserializer together with StringJsonMessageConverter.** The deserializer already creates an object while the converter expects a JSON String. Use one consistent conversion strategy.

**Forgetting to set KafkaHeaders.TOPIC when sending a Message.** `KafkaTemplate` does not know the destination without a default topic. Set the topic explicitly or configure a default topic.

**Using RECEIVED_TOPIC for sending.** That is inbound metadata. Use `TOPIC` for outbound.

**Unsafe header casting.** Headers from other producers may arrive as `byte[]` or another type. Check the type and encoding before casting.

**Assuming all Kafka headers appear intact in MessageHeaders.** The mapper may convert types or merge duplicate-named headers. Use `ConsumerRecord.headers()` when native headers are needed.

**Using Object for every payload.** The listener loses compile-time type checking and may fail late. Use concrete types or validate a discriminator.

**Ignoring tombstones.** A null value is meaningful in a compacted topic. Accept raw `ConsumerRecord` if you need to distinguish keys and null values.

**Not distinguishing deserializer and converter errors.** Each failure occurs at a different stage. Place `ErrorHandlingDeserializer` or the container error handler at the right spot.

## 17. Message conversion design checklist

- [ ] Wire format and producer/consumer serializers/deserializers are defined.
- [ ] Serialization is clearly separated from `RecordMessageConverter`.
- [ ] Listeners accept payload, `Message<T>`, or `ConsumerRecord` based on actual needs.
- [ ] Inbound metadata uses the proper `KafkaHeaders.RECEIVED_*` and `OFFSET` constants.
- [ ] Outbound messages use `TOPIC`, `MESSAGE_KEY`, and optional headers with proper types.
- [ ] Custom headers have a clear encoding and mapping policy.
- [ ] Sensitive or internal headers are not unintentionally propagated.
- [ ] Converter is compatible with the value type returned by the deserializer.
- [ ] JSON conversion is not executed twice.
- [ ] Batch listeners preserve per-record metadata.
- [ ] Tombstones/null payloads are handled intentionally.
- [ ] Deserialization, message conversion, and business errors have separate handling strategies.
- [ ] Integration tests verify payload, headers, and metadata through a broker.

## Conclusion

Message conversion is the bridge between a Kafka record and a Spring `Message<?>`. `RecordMessageConverter` converts a `ConsumerRecord` into a Spring Message on the inbound side and a Spring Message into a `ProducerRecord` on the outbound side. `MessagingMessageConverter` is commonly used to map payloads and metadata; JSON message converters can convert JSON String/`byte[]` into Java types. Clearly distinguish serializers/deserializers from message converters, use the right `KafkaHeaders` for inbound and outbound, choose listener signatures based on metadata needs, and test both payloads and headers. When raw Kafka metadata, duplicate headers, or tombstones are required, `ConsumerRecord` remains the right choice to preserve the full semantics of the original record.


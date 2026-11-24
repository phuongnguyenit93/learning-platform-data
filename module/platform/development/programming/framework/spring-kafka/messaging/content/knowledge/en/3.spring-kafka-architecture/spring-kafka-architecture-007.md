# Adapter Between Kafka Records and Spring Messages

Spring Kafka bridges two data models: **Kafka records** at the broker communication layer and **Spring Messages** at the Spring application layer. Adapters convert between these two models so the application can work with payloads and metadata using the familiar Spring Messaging API, while Kafka still receives and produces records according to its protocol.

Understanding this boundary helps you choose the right parameter types for `@KafkaListener`, send messages with `KafkaTemplate`, pass keys and metadata, and distinguish serialization errors from message conversion errors.

## 1. Why is an adapter needed?

Kafka producers and consumers work with records. A record has a key, value, headers, timestamp, and positional information such as topic, partition, and offset. A Spring application typically wants to pass a business object along with headers like correlation ID, event type, or routing information.

Spring Messaging represents data as `Message<T>` consisting of two parts:

- `payload`: the main content, such as an `OrderCreated` object.
- `headers`: metadata accompanying the payload, such as topic, key, correlation ID, or tracing info.

Spring Kafka provides adapters and converters to move data back and forth between the two models:

```mermaid
flowchart LR
    A[Spring Application] --> B[Message payload + headers]
    B --> C[KafkaTemplate + RecordMessageConverter]
    C --> D[ProducerRecord]
    D --> E[Kafka Serializer]
    E --> F[Kafka Broker]
    F --> G[Kafka Deserializer]
    G --> H[ConsumerRecord]
    H --> I[RecordMessageConverter]
    I --> J[Spring Message]
    J --> K[@KafkaListener]
```

On the sending side, the adapter creates a `ProducerRecord` from `Message<?>` before the Kafka serializer converts the key/value into bytes. On the receiving side, the Kafka deserializer turns bytes into key/value first; then the adapter can create a `Message<?>` for the listener to handle. The adapter is thus the integration boundary between the Kafka API and Spring Messaging.

## 2. Distinguishing Kafka Records and Spring Messages

These two data types serve closely related purposes but are not identical.

| Concept | Kafka record | Spring Message |
|---|---|---|
| Content | `value` | `payload` |
| Routing key | `key` | Typically represented via `KafkaHeaders.KEY` when sending |
| Custom metadata | Kafka `Headers` | `MessageHeaders` |
| Topic/partition | Record properties | Can be represented via dedicated Kafka headers |
| Offset | Record position in a partition | Receive header such as `KafkaHeaders.OFFSET` |
| Data type | `ProducerRecord<K,V>` or `ConsumerRecord<K,V>` | `Message<T>` |

`ConsumerRecord<K,V>` also provides raw properties such as topic, partition, offset, timestamp, key, value, and Kafka headers. `Message<T>` is the Spring-layer envelope: the payload has an application type and metadata is accessed via `MessageHeaders`.

Kafka headers and Spring message headers also have important differences. Kafka stores headers as pairs of name and byte array; a record can have multiple headers with the same name. `MessageHeaders` is a map keyed by header name, values can be Java objects, and each name holds a single value. Therefore, header conversion requires a mapping policy; you cannot assume the two structures preserve every characteristic of one another.

## 3. Components Performing Conversion

Spring Kafka includes several related components:

| Component | Responsibility |
|---|---|
| `KafkaTemplate<K,V>` | API for sending data to Kafka; supports sending records and sending Spring `Message<?>` |
| `ProducerRecord<K,V>` | Record sent by the Kafka producer to the broker |
| `ConsumerRecord<K,V>` | Record received by the Kafka consumer from the broker |
| `RecordMessageConverter` | Converts between `Message<?>` and Kafka records at the record level |
| `MessagingMessageConverter` | Converter integrating Spring Messaging with Kafka records, including payload and headers |
| `KafkaHeaderMapper` | Maps headers between `MessageHeaders` and Kafka `Headers` |
| `KafkaHeaders` | Set of specialized header names Spring Kafka uses for Kafka metadata |

For batch listeners, Spring Kafka also provides `BatchMessageConverter` to convert a batch of records into a message with a list payload and corresponding metadata.

`MessagingMessageConverter` is the standard integration choice when the application wants to use Spring Messages. If payload or metadata structure follows custom rules, you can supply a custom converter or header mapper. Customization should start from a specific conversion requirement, such as a special payload format or cross-service correlation header propagation rules.

## 4. Receiving Side: ConsumerRecord to Spring Message

The data receiving flow typically happens in this order:

1. The Kafka broker returns record bytes to the consumer.
2. Kafka deserializers convert key and value bytes into the configured Java types.
3. The Kafka client constructs a `ConsumerRecord<K,V>` holding the deserialized payload and record metadata.
4. Spring Kafka uses `RecordMessageConverter` to build a `Message<?>` if the listener expects the Spring Messaging model.
5. The listener adapter resolves the payload and headers into the parameters of the `@KafkaListener` method.

Example of a listener receiving a full Spring Message:

```java
@Component
public class OrderEventListener {

    @KafkaListener(
            topics = "orders",
            groupId = "order-read-model"
    )
    public void handle(Message<OrderCreated> message) {
        OrderCreated event = message.getPayload();

        String topic = message.getHeaders().get(
                KafkaHeaders.RECEIVED_TOPIC, String.class);
        Integer partition = message.getHeaders().get(
                KafkaHeaders.RECEIVED_PARTITION, Integer.class);
        Long offset = message.getHeaders().get(
                KafkaHeaders.OFFSET, Long.class);
        Object key = message.getHeaders().get(KafkaHeaders.RECEIVED_KEY);

        // Process event and use metadata for logging/tracing as needed.
    }
}
```

The payload is `OrderCreated`; routing and positional details are read from headers. Commonly used receive headers include:

| Header | Meaning |
|---|---|
| `KafkaHeaders.RECEIVED_TOPIC` | Topic containing the received record |
| `KafkaHeaders.RECEIVED_PARTITION` | Partition containing the record |
| `KafkaHeaders.OFFSET` | Offset of the record |
| `KafkaHeaders.RECEIVED_KEY` | Key of the received record, if present |
| `KafkaHeaders.RECEIVED_TIMESTAMP` | Timestamp of the received record |

Header names and types should be taken from the `KafkaHeaders` constants of the Spring Kafka version your project uses. The key value may be absent if the producer sent a keyless record; the listener should handle that case if the key is optional.

### Receiving only the payload and needed headers

Not every listener needs the entire `Message<?>` object. You can declare the payload and only the required headers directly:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-audit"
)
public void audit(
        @Payload OrderCreated event,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset,
        @Header(name = KafkaHeaders.RECEIVED_KEY, required = false) String key) {

    // Record event along with topic/partition/offset coordinates.
}
```

This style fits when the method only needs a few explicit metadata fields. `@Payload` designates business data; `@Header` instructs Spring to resolve a specific header. If a header may be absent, set `required = false` or use a nullable type.

### When the raw ConsumerRecord is needed

If a listener needs to interact directly with the Kafka API or needs full raw record details, it can accept `ConsumerRecord`:

```java
@KafkaListener(topics = "orders", groupId = "order-diagnostics")
public void inspect(ConsumerRecord<String, OrderCreated> record) {
    String topic = record.topic();
    int partition = record.partition();
    long offset = record.offset();
    String key = record.key();
    OrderCreated value = record.value();

    // Timestamp and record.headers() can also be read.
}
```

Choose `Message<T>` when the application wants to work with payload and metadata in the Spring model. Choose `ConsumerRecord<K,V>` when you need the full Kafka API or raw header processing. Both styles serve different needs; do not switch to `Message<?>` just to pull one extra field the listener does not use.

## 5. Sending Side: Spring Message to ProducerRecord

`KafkaTemplate` supports sending a Spring `Message<?>`. The converter reads the payload and specialized Kafka headers to build a `ProducerRecord`.

Example of sending an order event:

```java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreated event, String correlationId) {
        Message<OrderCreated> message = MessageBuilder
                .withPayload(event)
                .setHeader(KafkaHeaders.TOPIC, "orders")
                .setHeader(KafkaHeaders.KEY, event.orderId())
                .setHeader("correlationId", correlationId)
                .build();

        kafkaTemplate.send(message);
    }
}
```

In the example:

- `KafkaHeaders.TOPIC` specifies the target topic.
- `KafkaHeaders.KEY` specifies the record key, used by the partitioner.
- `correlationId` is an application-added business header for linking operations across services.
- The `OrderCreated` payload becomes the value of `ProducerRecord` after the converter processes it.

You can also set `KafkaHeaders.PARTITION` when the application needs to specify a particular partition with a clear business or operational reason. If omitted, the producer's partitioner selects the partition based on configuration and key. Avoid calculating partitions manually at the business layer when the partitioner can manage routing rules.

`KafkaTemplate` also offers direct send overloads such as `send(topic, key, value)`. Use those overloads when you only need to send a payload, topic, and key. Use `send(Message<?>)` when packaging a payload with multiple metadata fields in a Spring Message or integrating with other Spring Messaging components.

## 6. Distinguishing Converters from Serializers and Deserializers

This is a common point of confusion when configuring Spring Kafka. Converters and serializers/deserializers sit at two different boundaries.

| Component | Conversion | When it runs |
|---|---|---|
| `RecordMessageConverter` | Spring `Message<?>` ↔ Kafka `ProducerRecord`/`ConsumerRecord` | At the Spring Kafka adapter |
| Kafka `Serializer<K>` | Java key or value → bytes | Before the producer sends the record |
| Kafka `Deserializer<K>` | Bytes → Java key or value | After the consumer receives the record |
| `KafkaHeaderMapper` | Spring `MessageHeaders` ↔ Kafka `Headers` | When the adapter maps metadata |

For example, if the consumer is already configured with `JsonDeserializer<OrderCreated>`, the value inside `ConsumerRecord` is already an `OrderCreated` object. `MessagingMessageConverter` can place that object into the payload of `Message<OrderCreated>`. The converter does not need to decode JSON a second time.

If the consumer uses `StringDeserializer` or `ByteArrayDeserializer`, the payload after Kafka deserialization is still a `String` or `byte[]`. To turn JSON inside that payload into `OrderCreated`, the application needs an appropriate JSON conversion step, such as a JSON message converter or custom converter. Changing the listener parameter type to `Message<OrderCreated>` alone does not automatically guarantee bytes/strings are decoded into the right POJO.

The sending side is analogous: `RecordMessageConverter` prepares a record holding Java key/value objects; the Kafka serializer is what converts key/value into bytes. Therefore, `KafkaTemplate<String, OrderCreated>` configuration must be compatible with producer serializers, and the key/value types expected by the listener must match consumer deserializers.

Example configuration using Spring Kafka's JSON serializer/deserializer:

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
        spring.json.trusted.packages: "com.example.orders"
        spring.json.value.default.type: "com.example.orders.OrderCreated"
```

This is an illustrative configuration for a single concrete value type. In systems with multiple event types, design proper type mapping or deserializer configuration rather than defaulting every record to `OrderCreated`. Declare trusted packages only for packages the application genuinely trusts.

## 7. Header Mapping and Metadata Propagation

Headers carry information for routing, tracing, or processing without embedding everything into the payload. For example, an event might carry `correlationId`, `traceparent`, `tenantId`, or `eventType`.

Kafka stores headers as names and byte arrays. Spring Message allows headers to carry Java values. `KafkaHeaderMapper` is responsible for converting between the two representations. Spring Kafka typically uses `DefaultKafkaHeaderMapper` for header mapping in the Spring Messaging model.

Example of an application sending a correlation ID:

```java
Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, "orders")
        .setHeader(KafkaHeaders.KEY, event.orderId())
        .setHeader("correlationId", correlationId)
        .setHeader("eventType", "OrderCreated")
        .build();

kafkaTemplate.send(message);
```

The receiving listener can read business headers:

```java
@KafkaListener(topics = "orders", groupId = "order-audit")
public void handle(Message<OrderCreated> message) {
    String correlationId = message.getHeaders().get(
            "correlationId", String.class);
    String eventType = message.getHeaders().get(
            "eventType", String.class);

    // Process mapped payload and metadata.
}
```

Points to remember when designing headers:

- `KafkaHeaders.TOPIC`, `KEY`, `PARTITION`, and `TIMESTAMP` are control headers used by the converter to populate record metadata. They are not ordinary custom business headers.
- `KafkaHeaders.RECEIVED_TOPIC`, `RECEIVED_PARTITION`, `RECEIVED_KEY`, and `OFFSET` are headers Spring Kafka populates when receiving records.
- Custom headers like `correlationId` are mapped to Kafka headers according to the header mapper configuration.
- Kafka allows multiple headers with the same name, whereas Spring `MessageHeaders` is a map and cannot fully represent multiple values per name in the same way.
- Not every internal Spring header should be transmitted over the broker. Framework headers may be recreated on the receiving side or filtered out by mapper rules.

If mapping behavior needs adjustment, you can configure a custom `KafkaHeaderMapper` or tune `DefaultKafkaHeaderMapper` rules. Agree on header names, types, and formats between producers and consumers, especially when the two sides are written in different languages or frameworks. In polyglot systems, explicit byte/string or JSON header conventions are usually easier to interoperate with than relying on Spring-specific Java type metadata.

## 8. Configuring Converters on Listener Containers

The listener container can use `RecordMessageConverter` to convert received records into Spring Messages. When explicit configuration is needed, attach the converter to `ConcurrentKafkaListenerContainerFactory`:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            orderKafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setRecordMessageConverter(new MessagingMessageConverter());
        return factory;
    }
}
```

The listener selects the factory by its corresponding name:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-read-model",
        containerFactory = "orderKafkaListenerContainerFactory"
)
public void handle(Message<OrderCreated> message) {
    // Process Spring Message.
}
```

To send `Message<?>`, you can attach the corresponding converter to `KafkaTemplate` if the application wants explicit configuration:

```java
@Bean
KafkaTemplate<String, OrderCreated> orderKafkaTemplate(
        ProducerFactory<String, OrderCreated> producerFactory) {

    var template = new KafkaTemplate<>(producerFactory);
    template.setMessageConverter(new MessagingMessageConverter());
    return template;
}
```

In a Spring Boot application, check how auto-configuration creates `KafkaTemplate` and the listener container before declaring custom beans. If default behavior suffices, there is no need to create extra factories or templates. When custom factory configurations exist, make sure listeners point to the right `containerFactory`; otherwise, the configured converter may not be used.

## 9. Batch Listeners and List-Shaped Headers

With batch listeners, a single poll can return multiple records. A batch converter can transform them into a message with a list payload:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-batch-reader",
        containerFactory = "batchKafkaListenerContainerFactory"
)
public void handleBatch(Message<List<OrderCreated>> message) {
    List<OrderCreated> events = message.getPayload();

    // Process events in the batch.
}
```

Metadata corresponding to individual records can be represented as lists in headers, depending on configuration and the batch converter. Do not read a single scalar header as if it always represented the entire batch. When per-record partition, offset, or key precision is required, use the list-based header structures provided by the converter or accept `List<ConsumerRecord<K,V>>` directly if raw record data is needed.

Batch listeners suit aggregating work or optimizing batch operations. In return, handler code must manage errors and progress at the batch level; a single failing record can affect how the whole batch is committed or retried depending on container and error handler configuration.

## 10. Common Errors at the Adapter Boundary

**Missing topic when sending `Message<?>`:** the converter needs the target topic from the `KafkaHeaders.TOPIC` header or the template's default topic configuration. Check configuration if the send call does not specify a topic.

**Using the wrong key header on the receiving side:** send uses `KafkaHeaders.KEY`; receive should read `KafkaHeaders.RECEIVED_KEY`. Using the wrong header name can cause the listener to receive `null` even when the record has a key.

**Confusing converter with deserializer:** a converter does not replace a Kafka deserializer. If the consumer receives `byte[]` or `String`, check the value deserializer before investigating the converter.

**Payload has the wrong type:** generic `Message<OrderCreated>` does not magically turn the payload into `OrderCreated`. Check serializers/deserializers and any JSON conversion step.

**Custom headers fail to reach the consumer:** check the header mapper, header filtering rules, and whether the data type can be serialized to bytes. Also verify header names on both producer and consumer.

**Losing duplicate-named headers:** Kafka allows multiple headers with the same name, whereas Spring's map keeps only one value per name. If business logic requires multiple values, adopt another encoding convention or read Kafka headers from `ConsumerRecord`.

**Misusing topic/partition/offset metadata:** received metadata is `RECEIVED_TOPIC`, `RECEIVED_PARTITION`, and `OFFSET`. These values describe the received record, not metadata for a subsequent send.

**Conversion failing before entering the listener:** deserialization or message conversion errors can happen before the listener method is invoked. When investigating, separate logs and metrics by stage: Kafka deserialization, record conversion, argument binding, and business processing.

## 11. Choosing the Right Way to Receive Messages

| Reception style in `@KafkaListener` | When to use | Characteristics |
|---|---|---|
| `OrderCreated` | Only business data is needed | Concise, minimal coupling to Kafka metadata |
| `Message<OrderCreated>` | Payload plus multiple headers needed | Follows the Spring Messaging model |
| `@Payload` combined with `@Header` | Specific metadata fields needed | Makes method dependencies explicit |
| `ConsumerRecord<String, OrderCreated>` | Raw Kafka record needed | Direct access to topic, partition, offset, key, and headers |
| `Message<List<OrderCreated>>` | Batch processing in Spring Message model | Payload is a list; headers may contain per-record data |

There is no single best parameter style for every listener. Start from the information business logic genuinely needs. If logic is independent of Kafka, accepting the payload keeps the method easy to reuse and test. If logic needs a correlation ID or record coordinates, use `Message<T>` or `@Header`. Reserve `ConsumerRecord` for cases requiring Kafka-level access.

## 12. End-to-End Flow Example

Suppose the order service emits `OrderCreated` and the read model service updates the order view. The producer sends `orderId` as the key and `correlationId` as a header. The consumer receives a Spring Message to read the payload, topic, partition, offset, and correlation ID.

```java
@Service
public class OrderPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderPublisher(KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreated event, String correlationId) {
        Message<OrderCreated> message = MessageBuilder
                .withPayload(event)
                .setHeader(KafkaHeaders.TOPIC, "orders")
                .setHeader(KafkaHeaders.KEY, event.orderId())
                .setHeader("correlationId", correlationId)
                .build();

        kafkaTemplate.send(message);
    }
}

@Component
public class OrderProjectionListener {

    @KafkaListener(topics = "orders", groupId = "order-projection")
    public void onMessage(Message<OrderCreated> message) {
        OrderCreated event = message.getPayload();
        String correlationId = message.getHeaders().get(
                "correlationId", String.class);
        String topic = message.getHeaders().get(
                KafkaHeaders.RECEIVED_TOPIC, String.class);
        Integer partition = message.getHeaders().get(
                KafkaHeaders.RECEIVED_PARTITION, Integer.class);
        Long offset = message.getHeaders().get(
                KafkaHeaders.OFFSET, Long.class);

        // Update read model from event.
        // Log correlationId and record coordinates for tracing.
    }
}
```

The data flow can be summarized as follows:

1. The producer builds a Spring Message from the event and metadata.
2. `KafkaTemplate` together with its converter creates a `ProducerRecord`.
3. Kafka serializers convert key/value to bytes and the producer sends the record.
4. The consumer receives the record; deserializers produce Java key/value objects.
5. Spring Kafka converts the record into a Spring Message for the listener.
6. The listener reads the payload and headers for business processing, logging, or tracing.

The example assumes producer and consumer agree on the `OrderCreated` data type and compatible JSON serializer/deserializer settings. In real systems, align schemas, event versions, and header formats across services.

## 13. Checklist When Designing Adapters

- Java payload is supported by serializers/deserializers on both sides with compatible schemas.
- Clearly distinguish converters, serializers, deserializers, and header mappers.
- Producer sets `KafkaHeaders.TOPIC` and `KafkaHeaders.KEY` intentionally when sending `Message<?>`.
- Consumer reads incoming metadata via `RECEIVED_TOPIC`, `RECEIVED_PARTITION`, `RECEIVED_KEY`, and `OFFSET`.
- Business headers have consistent names, types, and formats across services.
- Header mapper rules are verified when propagating correlation IDs, trace context, or custom metadata.
- Listeners accept `ConsumerRecord` only when low-level Kafka APIs are genuinely needed.
- Batch listeners handle per-record headers properly and understand batch commit/retry scopes.
- Logs or metrics distinguish deserialization errors, conversion errors, binding errors, and business errors.

The adapter between Kafka records and Spring Messages lets applications use a consistent payload/header model across the Spring ecosystem. When conversion boundaries are clear, teams can select the right API types, configure serializers and converters accurately, and propagate metadata across services in a controlled way.

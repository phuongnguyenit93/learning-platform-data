# Kafka headers and Spring MessageHeaders

A Kafka record does not only have a key and a value. Each record can also carry **headers** to pass auxiliary information such as correlation ID, trace context, event type, contract version, or source service. Headers help components coordinate and trace processing flows without stuffing all metadata into the business payload.

At the Kafka layer, a header is a name and byte-valued pair. At the Spring Messaging layer, applications typically work with **MessageHeaders**, where header values are Java objects and can be mapped to Kafka headers through a KafkaHeaderMapper. The two models are related but not identical: understanding how conversions work between them helps avoid data type errors, lost metadata, or accidentally sending internal headers to the broker.

This lesson belongs to the **Headers and metadata** chapter of the **SPRING_KAFKA_MESSAGING** module, focusing on how to create, send, receive, and map Kafka headers in Spring Kafka, while designing metadata useful for tracing, operations, and cross-service compatibility.

## Learning Outcomes

After this lesson, you can:

- Explain the header structure in a Kafka record and the characteristics of `byte[]`.
- Distinguish Kafka headers, record metadata, and Spring MessageHeaders.
- Create headers using ProducerRecord and KafkaTemplate.
- Send a Spring Message via KafkaTemplate with KafkaHeaders.
- Read headers using ConsumerRecord, @Header, and @Headers.
- Understand the role of DefaultKafkaHeaderMapper and SimpleKafkaHeaderMapper.
- Handle duplicate header names, encoding, and data types.
- Propagate correlation ID and trace context across services.
- Design allowlists, avoid exposing sensitive data, and test header mapping.

## 1. What components make up a Kafka record?

A Kafka record has a key, value, timestamp, and headers. The key/value are serialized into bytes according to the serializer configured on the producer; headers are also stored as names and byte values.

The structure can be visualized as:

~~~text
Kafka record
├── key        -> bytes (nullable)
├── value      -> bytes (nullable)
├── timestamp  -> record timestamp
└── headers
    ├── correlation_id -> UTF-8 bytes
    ├── event_type     -> UTF-8 bytes
    └── traceparent    -> UTF-8 bytes
~~~

Example of an OrderCreated event:

| Component | Example | Purpose |
|---|---|---|
| Key | order-1001 | Partition routing and preserving order per order. |
| Value | JSON OrderCreatedEvent | Business content. |
| Timestamp | 2026-11-17T03:30:00Z | Record timestamp according to the timestamp policy. |
| correlation_id | corr-82a1 | Correlates logs across a request flow. |
| event_type | OrderCreated | Identifies the event type. |
| event_version | 2 | Supports selecting the contract or compatibility logic. |
| traceparent | W3C trace context | Links distributed traces. |

Headers are auxiliary metadata for a record. You should not move all business data into headers: the payload remains the place for structured and versioned event content.

## 2. Characteristics of Kafka Headers

Kafka uses the `Headers` interface and implementations such as `RecordHeaders`. Each header has:

- A name as a String.
- A value as `byte[]`; the value can be empty or null depending on how the record is created.
- A position in the header list.

Kafka allows multiple headers with the same name on the same record. This is useful when a record needs to carry multiple values of the same kind, though the consumer must define how to read them.

Example:

~~~java
ProducerRecord<String, String> record =
        new ProducerRecord<>(
                "orders.created",
                "order-1001",
                "{\"orderId\":\"order-1001\"}"
        );

record.headers()
        .add("correlation_id", "corr-82a1".getBytes(StandardCharsets.UTF_8))
        .add("event_type", "OrderCreated".getBytes(StandardCharsets.UTF_8))
        .add("event_version", "2".getBytes(StandardCharsets.UTF_8));

kafkaTemplate.send(record);
~~~

This code snippet uses a Kafka ProducerRecord and adds headers before sending. For text headers, UTF-8 encoding should be agreed upon by both producer and consumer.

Reading a header from a ConsumerRecord:

~~~java
Header header = record.headers().lastHeader("correlation_id");

String correlationId = header == null
        ? null
        : new String(header.value(), StandardCharsets.UTF_8);
~~~

Commonly used APIs:

| API | Meaning |
|---|---|
| add(key, value) | Adds a header; does not automatically replace headers with the same name. |
| lastHeader(key) | Retrieves the last header with that name. |
| headers(key) | Retrieves all headers with the same name in order. |
| remove(key) | Removes all headers with the matching name. |
| toArray() | Returns headers as an array for iteration. |

If headers share the same name, `lastHeader` only returns the single last value. When the contract allows multiple values, use `headers(name)` and process the entire list.

## 3. How are headers different from record metadata?

Kafka headers are attached to the record by the producer. Some other information is provided by the Kafka broker or consumer as record metadata, rather than custom headers.

| Information | Where it resides | Example |
|---|---|---|
| correlation_id | Kafka record header | corr-82a1 |
| event_type | Kafka record header | OrderCreated |
| topic | Record metadata / ConsumerRecord | orders.created |
| partition | Record metadata / ConsumerRecord | 2 |
| offset | Record metadata / ConsumerRecord | 145 |
| timestamp | Record metadata / ConsumerRecord | Record timestamp |
| consumer group | Consumer configuration and group metadata | orders-fulfillment |

The producer can set a timestamp when creating a ProducerRecord, but the broker may apply the topic's timestamp policy to determine the stored timestamp. Topic, partition, and offset are determined during record sending/writing; they are not custom headers arbitrarily set by the application to replace real metadata.

In Spring Kafka, some record metadata is mapped into Spring MessageHeaders upon receiving a message, such as `KafkaHeaders.RECEIVED_TOPIC`, `RECEIVED_PARTITION`, `OFFSET`, and `RECEIVED_TIMESTAMP`. These Spring header names are how the framework presents metadata to the application; they do not mean the broker stored those fields as custom Kafka headers.

## 4. Spring Message and MessageHeaders

Spring Messaging represents a message with a payload and headers:

~~~text
org.springframework.messaging.Message
├── payload
└── MessageHeaders
    ├── id
    ├── timestamp
    ├── kafka_topic
    ├── kafka_messageKey
    └── correlation_id
~~~

MessageHeaders is an immutable map after the message is created. If you need to build a new message or add headers, use MessageBuilder instead of modifying the map directly.

Example:

~~~java
Message<OrderCreatedEvent> message = MessageBuilder
        .withPayload(event)
        .setHeader("correlation_id", "corr-82a1")
        .setHeader("event_type", "OrderCreated")
        .setHeader("event_version", "2")
        .build();
~~~

MessageHeaders can hold many Java value types such as String, Integer, UUID, or other objects. Kafka headers only store `byte[]`, so sending a message via Spring Kafka requires a mapping and conversion mechanism.

Spring internal headers such as `id` and `timestamp` are not necessarily sent to Kafka. The header mapper applies filtering and conversion rules; do not assume every entry in MessageHeaders becomes a record header.

## 5. What is KafkaHeaders?

Spring Kafka defines the `KafkaHeaders` class containing standard header names to pass information between Spring Message and Kafka.

Some common constants:

| Constant | Role |
|---|---|
| KafkaHeaders.TOPIC | Target topic when sending a message. |
| KafkaHeaders.PARTITION | Target partition if specified by the application. |
| KafkaHeaders.MESSAGE_KEY | Key of the outbound record. |
| KafkaHeaders.TIMESTAMP | Outbound timestamp if set. |
| KafkaHeaders.RECEIVED_TOPIC | Topic of the received record. |
| KafkaHeaders.RECEIVED_PARTITION | Partition of the received record. |
| KafkaHeaders.OFFSET | Offset of the received record. |
| KafkaHeaders.RECEIVED_TIMESTAMP | Timestamp of the received record. |
| KafkaHeaders.RECEIVED_KEY | Key of the received record. |

These constants help code avoid hardcoding transport header names. Specific names and APIs should be checked against the Spring Kafka version used by the project.

`KafkaHeaders.TOPIC`, `MESSAGE_KEY`, and `PARTITION` are outbound control headers for sending messages. `RECEIVED_TOPIC`, `RECEIVED_PARTITION`, `OFFSET`, and `RECEIVED_KEY` are metadata injected into the message by the framework when receiving a record.

Do not confuse `KafkaHeaders` with custom header names defined by the application itself, such as `correlation_id` or `event_type`.

## 6. Sending messages with KafkaTemplate and Spring Message

KafkaTemplate supports sending a Spring Message. The application can set the topic, key, partition, and custom metadata in MessageHeaders.

Example:

~~~java
@Service
public class OrderPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
            OrderCreatedEvent event,
            String correlationId) {

        Message<OrderCreatedEvent> message = MessageBuilder
                .withPayload(event)
                .setHeader(KafkaHeaders.TOPIC, "orders.created")
                .setHeader(KafkaHeaders.MESSAGE_KEY, event.orderId())
                .setHeader("correlation_id", correlationId)
                .setHeader("event_type", "OrderCreated")
                .setHeader("event_version", "2")
                .build();

        return kafkaTemplate.send(message);
    }
}
~~~

In the example:

- The payload is `OrderCreatedEvent`.
- `KafkaHeaders.TOPIC` determines the target topic.
- `KafkaHeaders.MESSAGE_KEY` sets the record key.
- `correlation_id` helps correlate logs across services.
- `event_type` and `event_version` describe the contract type and version.

If you need to specify a partition or timestamp, you can add `KafkaHeaders.PARTITION` and `KafkaHeaders.TIMESTAMP` according to the API of the version in use. Manually specifying a partition makes the producer bypass the normal key distribution strategy, so only use it when there is a clear architectural requirement.

## 7. Sending with ProducerRecord when direct header control is needed

If you need exact control over `byte[]`, multiple headers with the same name, or direct interaction with the Kafka API, use `ProducerRecord`.

~~~java
ProducerRecord<String, OrderCreatedEvent> record =
        new ProducerRecord<>(
                "orders.created",
                event.orderId(),
                event
        );

record.headers().add(
        new RecordHeader(
                "correlation_id",
                correlationId.getBytes(StandardCharsets.UTF_8)
        )
);

record.headers().add(
        new RecordHeader(
                "event_type",
                "OrderCreated".getBytes(StandardCharsets.UTF_8)
        )
);

kafkaTemplate.send(record);
~~~

ProducerRecord allows the application to add, iterate over, or remove headers before sending. This approach is also suitable when ensuring header values are a specific byte sequence without going through the Spring mapper's JSON conversion.

Do not mix both sending approaches in the same flow without agreeing on a convention. If one producer uses MessageHeaders with a mapper and another producer writes raw bytes directly, the consumer needs to know how to decode the corresponding headers.

## 8. Receiving headers with @Header and @Headers

With `@KafkaListener`, Spring Kafka can map metadata and custom headers into listener parameters.

Example:

~~~java
@Component
public class OrderCreatedListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-fulfillment"
    )
    public void consume(
            @Payload OrderCreatedEvent event,
            @Header(value = KafkaHeaders.RECEIVED_KEY, required = false) String key,
            @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
            @Header(KafkaHeaders.RECEIVED_PARTITION) Integer partition,
            @Header(KafkaHeaders.OFFSET) Long offset,
            @Header(name = "correlation_id", required = false)
                    String correlationId,
            @Headers MessageHeaders headers) {

        log.info(
                "Received eventId={}, key={}, topic={}, partition={}, " +
                "offset={}, correlationId={}",
                event.eventId(),
                key,
                topic,
                partition,
                offset,
                correlationId
        );

        orderService.handle(event);
    }
}
~~~

Explanation:

- `@Payload` receives the deserialized object.
- `@Header` retrieves a specific header by name.
- `required=false` allows an optional header to be absent.
- `@Headers` receives the `MessageHeaders` collection to access multiple metadata entries.
- `KafkaHeaders.RECEIVED_*` are headers created by Spring Kafka when receiving a record.

If the key can be null, make the key parameter optional or use a type compatible with the contract. Do not assume every record has a key.

Another way is to receive `ConsumerRecord` directly:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-fulfillment"
)
public void consume(ConsumerRecord<String, OrderCreatedEvent> record) {
    Header header = record.headers().lastHeader("correlation_id");

    String correlationId = header == null
            ? null
            : new String(header.value(), StandardCharsets.UTF_8);

    orderService.handle(
            record.value(),
            record.topic(),
            record.partition(),
            record.offset(),
            correlationId
    );
}
~~~

ConsumerRecord allows direct access to Kafka headers and metadata without mapping them into Spring MessageHeaders. Choose the receiving approach based on your needs: MessageHeaders is convenient for Spring Messaging; ConsumerRecord is useful when granular Kafka API control is needed.

## 9. KafkaHeaderMapper converts between the two models

KafkaHeaderMapper is responsible for mapping between Spring MessageHeaders and Kafka Headers. When using a message converter, the mapper converts Java values into `byte[]` for sending and converts received `byte[]` into values inside Spring MessageHeaders.

Two common mappers:

| Mapper | Characteristics | When appropriate |
|---|---|---|
| DefaultKafkaHeaderMapper | Supports converting multiple object types, can use JSON and type metadata | Applications that need to pass typed Java headers via Spring Message. |
| SimpleKafkaHeaderMapper | Focuses on String and byte[] | Simple header contracts, wanting explicit byte control. |

DefaultKafkaHeaderMapper can write type metadata for serialized headers so the receiving side can restore the Java type. Restoration depends on type mapping, trusted packages, and mapper configuration. You should not trust every class declared in headers from untrusted sources.

SimpleKafkaHeaderMapper is suitable when services standardize on String or `byte[]` headers. This approach reduces dependency on Java classes across applications written in different languages or versions.

If the application needs explicit mapper configuration, you can create a `MessagingMessageConverter` and attach the corresponding `KafkaHeaderMapper` to the listener container factory or `KafkaTemplate` according to the configuration of the Spring Kafka version in use. Many default configurations already create a converter and mapper; only customize when there are specific mapping requirements.

## 10. Header type mapping and cross-service compatibility

A header in MessageHeaders can be an Integer, UUID, or object, but when crossing Kafka it becomes `byte[]`. If the sender uses `DefaultKafkaHeaderMapper`, the mapper can include type metadata so the receiver converts it back to the corresponding object.

This is convenient when two services share the Java ecosystem, but creates coupling if a service depends on specific class names or packages of the publishing service.

Example of not passing complex internal objects:

~~~java
.setHeader("customer_context", internalCustomerContext)
~~~

Another service may not have the `InternalCustomerContext` class, or the class package may have changed. Header deserialization can fail even though the business payload is still valid.

Prefer simple header contracts:

- String for correlation ID, event type, tenant reference.
- `Byte[]` for binary data that needs an explicit definition.
- Numeric strings or timestamps in a standard format if cross-language exchange is required.
- W3C trace context for distributed tracing.

If typed headers are needed, publish schemas and encoding rules independent of Java class names. Avoid treating mapper type metadata as a schema registry for the entire event contract.

## 11. Correlation ID and distributed tracing

Correlation ID helps link logs or events belonging to the same business request. For example, the API receives an order creation request, the producer sends `OrderCreatedEvent` with `correlation_id`; fulfillment and notification continue propagating this ID in their logs and outbound events.

~~~mermaid
flowchart LR
    API[Order API] -->|correlation_id| K[Kafka topic]
    K --> F[Fulfillment service]
    K --> A[Analytics service]
    F -->|propagate context| N[Notification service]
    A -->|propagate context| R[Reporting]
~~~

Correlation ID is a business or request correlation identifier. Distributed tracing typically uses `traceparent` and `tracestate` following the W3C standard to link spans across processes.

If the application uses Micrometer Tracing, OpenTelemetry, or Kafka-compatible instrumentation, let the tracing library manage context injection/extraction as configured. Do not generate a random trace ID at each hop if the goal is to maintain a single end-to-end trace.

When creating a new event from a received event, clearly define which context should continue to propagate and which context should be newly created. A new business operation may have a new correlation ID while remaining linked to the previous trace or parent context according to tracing rules.

Do not use correlation ID in place of `eventId`. An event ID identifies a specific event; a correlation ID links multiple operations within the same flow.

## 12. Forwarding headers when producing new events

A service often receives an event and then publishes another event. Forwarding headers can preserve the correlation ID, trace context, and some source information, but you should not blindly copy every header.

Example of allowlisting headers permitted to propagate:

~~~java
Set<String> allowedHeaders = Set.of(
        "correlation_id",
        "traceparent",
        "tracestate",
        "tenant_reference"
);

ProducerRecord<String, OrderProcessedEvent> outbound =
        new ProducerRecord<>(
                "orders.processed",
                processed.orderId(),
                processed
        );

record.headers().forEach(header -> {
    if (allowedHeaders.contains(header.key())) {
        byte[] value = header.value();
        outbound.headers().add(
                new RecordHeader(
                        header.key(),
                        value == null ? null : Arrays.copyOf(value, value.length)
                )
        );
    }
});

kafkaTemplate.send(outbound);
~~~

An allowlist helps control which metadata crosses service boundaries. Do not automatically forward internal headers such as deserialization exception info, DLT metadata, retry management headers, or technical headers that only have meaning within a single container.

If a header contains tenant or security context, validate the value from a trusted source and do not use headers arbitrarily set by a producer as proof of authorization. Kafka headers are sender-supplied data; consumers must treat them as potentially invalid or spoofed input.

## 13. Naming conventions and encoding

A clear header convention helps services exchange metadata consistently.

Example:

| Header | Encoding | Convention |
|---|---|---|
| correlation_id | UTF-8 | Request flow correlation ID. |
| event_type | UTF-8 | Event type name according to the contract. |
| event_version | UTF-8 | Schema or event contract version. |
| traceparent | ASCII/UTF-8 per W3C | Distributed trace context. |
| tenant_reference | UTF-8 | Business-validated tenant reference code. |
| source_service | UTF-8 | Name of the service publishing the event. |

Principles:

- Choose consistent names and avoid multiple aliases for the same meaning.
- Define encoding clearly, typically UTF-8 for text.
- Define required and optional values.
- Define maximum lengths and how missing values are handled.
- Use `event_version` for the event contract rather than relying solely on class names.
- Avoid putting large payloads into headers.
- Do not use headers to store passwords, tokens, or unnecessary personal data.

Kafka headers are part of the record and increase transmitted/stored data size. Oversized headers can cause a record to exceed broker or producer message/request limits. Keep headers small and purposeful.

## 14. Headers and security

Headers are often viewed as secondary metadata, but they can contain sensitive information or affect how a consumer routes and processes messages.

Risks to control:

- Headers containing access tokens, session tokens, or credentials.
- Headers containing emails, phone numbers, or personal data.
- Producers spoofing `tenant_reference` or `source_service`.
- Type headers leading the consumer to deserialize an unauthorized class.
- Consumers trusting `event_type` or version without validating the payload.
- Logging all headers and leaking sensitive data or trace context.

Measures:

- Only transmit the minimum necessary metadata.
- Never place secrets into Kafka headers.
- Authorize permissions based on trusted security mechanisms, not custom headers.
- Restrict trusted packages and type mapping when using `DefaultKafkaHeaderMapper`.
- Use ACLs to restrict producer/consumer access to topics.
- Filter headers before logging and before forwarding to other services.
- Define header allowlists for each event stream.
- Apply appropriate retention and access controls to topics containing sensitive metadata.

Headers do not replace TLS, SASL, ACLs, or schema validation.

## 15. Testing Kafka headers and Spring MessageHeaders

Testing should verify both the byte headers on the Kafka record and the values after Spring maps them into `MessageHeaders`.

Test layers:

| Test | What to verify |
|---|---|
| ProducerRecord test | Header name and `byte[]` are created properly. |
| Duplicate header test | Multiple headers with the same name are preserved and read in order. |
| KafkaTemplate Message test | `KafkaHeaders.TOPIC` and `MESSAGE_KEY` control the record properly. |
| ConsumerRecord test | Raw byte headers and record metadata are read accurately. |
| MessageHeaders mapping test | Strings/objects are converted properly by the mapper. |
| Type mapping test | Typed headers are decoded according to configuration and allowlist. |
| Forwarding test | Only allowlisted headers are forwarded. |
| Trace propagation test | `traceparent`/correlation ID are preserved across services. |
| Security test | Secrets or untrusted headers are not used for access control. |

Example test for sending and reading a header with a consumer:

~~~java
ProducerRecord<String, String> record =
        new ProducerRecord<>(
                "orders.created",
                "order-1001",
                "payload"
        );

record.headers().add(
        "correlation_id",
        "corr-82a1".getBytes(StandardCharsets.UTF_8)
);

kafkaTemplate.send(record).get(10, TimeUnit.SECONDS);

ConsumerRecord<String, String> received =
        KafkaTestUtils.getSingleRecord(
                consumer,
                "orders.created",
                Duration.ofSeconds(10)
        );

Header receivedHeader =
        received.headers().lastHeader("correlation_id");

assertThat(receivedHeader).isNotNull();
assertThat(new String(
        receivedHeader.value(),
        StandardCharsets.UTF_8
)).isEqualTo("corr-82a1");
~~~

This test verifies that byte headers are actually written and read back. If testing the `MessageHeaders` mapper, send via `KafkaTemplate.send(Message<?>)` and receive via a listener accepting `Message<?>` or `@Header` parameters to verify header types and names after mapping.

You can use EmbeddedKafka for fast integration tests or Testcontainers when you need to test broker configurations close to production. Do not use fixed `Thread.sleep`; use explicit timeouts and synchronization conditions.

## 16. Common pitfalls

| Mistake | Consequence | How to handle |
|---|---|---|
| Sending String while consumer reads as byte[] or vice versa without agreement | Incorrect header decoding | Standardize encoding and mapper on both sides. |
| Assuming MessageHeaders and Kafka Headers are identical | Lost or mistyped headers on send | Understand the mapper and conversion rules. |
| Using lastHeader when a header has multiple values | Only reads the last value | Use `headers(name)` if the contract allows multiple values. |
| Using Java classes in headers as an inter-service contract | Package/version coupling between services | Use stable event names and versions. |
| Forwarding every received header | Leaks internal metadata or sensitive data | Use an allowlist. |
| Trusting tenant or role from a custom header | Can create authorization vulnerabilities | Authenticate via trusted security mechanisms. |
| Putting large payloads in headers | Bloats records and increases transmission cost | Put business data in the payload. |
| Confusing KafkaHeaders.OFFSET with a custom Kafka header | Misunderstanding record metadata | Distinguish Spring-mapped metadata headers from Kafka record headers. |
| Logging all headers | Leaks tokens or sensitive data | Filter and mask values before logging. |

## 17. Capstone exercise: propagating metadata for OrderCreatedEvent

Build a producer and consumer for the `orders.created` topic.

Requirements:

1. Send `OrderCreatedEvent` using `KafkaTemplate`.
2. Set the key to `orderId`.
3. Add `correlation_id`, `event_type`, and `event_version`.
4. Send once using `ProducerRecord` and once using a Spring `Message`.
5. Receive the event using `ConsumerRecord` and read raw Kafka headers.
6. Receive the event using `@KafkaListener` with `@Header` and `@Headers`.
7. Check `KafkaHeaders.RECEIVED_TOPIC`, `RECEIVED_PARTITION`, `OFFSET`, and `RECEIVED_KEY`.
8. Add two headers with the same name and verify `lastHeader` as well as `headers(name)`.
9. Configure a header mapper for String and object headers if required by the use case.
10. Forward `correlation_id` and trace context according to an allowlist to `orders.processed`.
11. Try sending an invalid header or wrong encoding and verify consumer handling.
12. Verify that headers are not used as an authorization mechanism.
13. Write an integration test with EmbeddedKafka or Testcontainers to check the round-trip.
14. Track the correlation ID across the producer, consumer, and downstream service.

The exercise is complete when metadata is sent, received, and mapped consistently; the consumer can trace records via correlation ID; and internal and sensitive headers are controlled.

## 18. Learning path and completion criteria

| Stage | Core content | Self-check criteria |
|---|---|---|
| 1. Kafka Headers | Header name and byte[] | Can create and read headers on ProducerRecord/ConsumerRecord. |
| 2. Record metadata | Topic, partition, offset, timestamp | Distinguish broker metadata from custom headers. |
| 3. Spring Message | Message and MessageHeaders | Build messages using MessageBuilder. |
| 4. KafkaHeaders | Topic, key, partition, and received metadata | Send/receive using standard Spring Kafka headers. |
| 5. Header mapper | DefaultKafkaHeaderMapper and SimpleKafkaHeaderMapper | Understand String, byte[], and object conversions. |
| 6. Tracing | Correlation ID and trace context | Trace a flow across multiple services. |
| 7. Forwarding | Allowlist and header propagation | Only forward necessary metadata. |
| 8. Security | Trusted types, secrets, and untrusted headers | Do not use custom headers as proof of authorization. |
| 9. Testing | Header round-trip and mapping | Test bytes, data types, and duplicate headers. |

The lesson is complete when you can create Kafka headers, send them with `KafkaTemplate`, read them via `ConsumerRecord` or Spring `MessageHeaders`, distinguish custom headers from record metadata, and design safe propagation between services.

Kafka headers help enrich a record with context without modifying the business payload. Spring `MessageHeaders` enables applications to work conveniently with Java values; `KafkaHeaderMapper` is responsible for converting them into byte headers. When naming conventions, encoding, type mapping, and security policies are aligned, metadata supports tracing and operations without creating unnecessary coupling between services.


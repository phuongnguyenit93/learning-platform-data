# HeaderMapper and header mapping

A Kafka record has a key, value, and headers. The key usually participates in partition selection; the value carries the business payload; headers carry metadata accompanying the record such as correlation ID, trace context, content type, event version, or event source.

At the Kafka layer, each header is a pair of name and byte array. In Spring Messaging, headers are usually represented as objects inside `MessageHeaders`. `KafkaHeaderMapper` is the bridge converting between these two models. It determines which headers are transferred, how data types are converted, and how values are restored on the consumer side.

Header mapping matters when applications use `@KafkaListener`, `KafkaTemplate`, and message converters. If mapping is misconfigured, payloads may still be sent and received successfully while metadata is missing, wrong-typed, or incompatible with other services.

This lesson belongs to the **Message conversion** chapter of the **SPRING_KAFKA_MESSAGING** module. The module focuses on building applications that send and receive events with Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, understanding topics, partitions, offsets, and consumer groups; and also learning serialization, retries, dead-lettering, transactions, exactly-once, concurrency, and testing to run reliable messaging flows.

## 1. What is a Kafka header?

A Kafka header is metadata attached to a record. Each header has a string name and a byte array or null value. Kafka allows multiple headers with the same name in a single record.

For example, an order record can carry headers such as:

| Header | Example value | Purpose |
| --- | --- | --- |
| `correlation-id` | `req-8f31` | Correlates logs and requests across multiple services. |
| `traceparent` | Trace context | Propagates distributed tracing context. |
| `event-type` | `OrderCreated` | Identifies the event kind. |
| `event-version` | `2` | Selects the matching contract/schema. |
| `content-type` | `application/json` | Describes the payload format. |
| `source-service` | `order-service` | Identifies the service emitting the event. |

Headers do not replace the key or value. They are intended for small metadata that helps trace and interpret the payload. Headers also do not automatically determine the partition; the default partitioner uses the record key rather than reading headers.

A record can be visualized as follows:

~~~text
ProducerRecord
  topic: order-events
  key: order-100
  value: OrderCreated(...)
  headers:
    correlation-id -> UTF-8 bytes
    event-type     -> UTF-8 bytes
    event-version  -> UTF-8 bytes
    traceparent    -> UTF-8 bytes
~~~

The Kafka broker stores headers alongside the record. Any consumer authorized to read the record can also read its attached headers; secrets or sensitive credentials should not be placed in headers.

Mapping flow when using Spring Message:

~~~mermaid
flowchart LR
    A[Spring Message] --> B[Message converter]
    B --> C[Payload conversion]
    B --> D[KafkaHeaderMapper]
    D --> E[Byte-based Kafka Headers]
    C --> F[ProducerRecord]
    E --> F
    F --> G[Kafka broker]
    G --> H[ConsumerRecord]
    H --> I[Message converter]
    I --> J[Payload object and MessageHeaders]
~~~

## 2. Kafka Headers and Spring MessageHeaders

The two header models have different data representations:

| Characteristic | Kafka Headers | Spring MessageHeaders |
| --- | --- | --- |
| API | `org.apache.kafka.common.header.Headers` | `org.springframework.messaging.MessageHeaders` |
| Name | String | String |
| Value | byte[] or null | Object |
| Duplicate names | Can have multiple headers with the same name | Map holds only one value per key |
| Purpose | Metadata on a Kafka record | Metadata in a Spring Message |
| Conversion | Needs a mapper when passing through Spring Message conversion | Mapper converts into Kafka headers |

Kafka allows multiple headers with the same name in one record. For example, a record can contain multiple `tag` headers or multiple metadata entries in order. By contrast, `MessageHeaders` is a map and cannot directly represent multiple values for the same key.

If business logic needs to preserve multiple duplicate-named headers, read `ConsumerRecord.headers()` directly or define a rule to collect values into a collection. Do not assume converting through `MessageHeaders` always preserves all duplicate headers intact.

Kafka headers are always bytes. When reading a UTF-8 string, decode bytes explicitly:

~~~java
Header header = record.headers().lastHeader("correlation-id");

String correlationId = header == null
    ? null
    : new String(header.value(), StandardCharsets.UTF_8);
~~~

Do not call `toString()` directly on `byte[]` expecting the string content; the result will be the byte array's object representation, not the decoded text.

## 3. What does HeaderMapper do?

`KafkaHeaderMapper` defines how headers are converted between a Spring Message and a Kafka record. It handles only header metadata; payload conversion is handled by the message converter and serializer/deserializer.

Two mapping directions:

1. **Outbound:** Spring `MessageHeaders` are converted into Kafka Headers before the producer sends the record.
2. **Inbound:** Kafka Headers are converted into `MessageHeaders` when a consumer record is converted into a Spring Message.

Core methods of the mapper look like:

~~~java
void fromHeaders(MessageHeaders source, Headers target);
void toHeaders(Headers source, Map<String, Object> target);
~~~

Method names indicate the conversion direction:

- `fromHeaders`: from Spring headers to Kafka headers.
- `toHeaders`: from Kafka headers to a Spring header map.

`KafkaHeaderMapper` is an abstraction. Applications usually use built-in implementations rather than writing a mapper from scratch. Only implement a custom mapper when you need a specific wire format or mapping rules that standard implementations do not satisfy.

## 4. DefaultKafkaHeaderMapper

`DefaultKafkaHeaderMapper` is Spring Kafka's flexible implementation. It can map String and `byte[]` headers directly; other object types can be serialized to JSON via Jackson.

When object types need to be restored, the mapper can add type metadata in a special `spring_json_header_types` header. This metadata tells the consumer the original Java type of JSON-serialized headers.

Example Spring Message with object headers:

~~~java
Message<OrderCreated> message =
    MessageBuilder.withPayload(event)
        .setHeader("correlation-id", "req-8f31")
        .setHeader("attempt", 2)
        .setHeader("origin", new ServiceOrigin("order-service"))
        .build();
~~~

When the mapper converts to Kafka:

- `correlation-id` is a String and can be mapped as a string.
- `attempt` is an Integer and can be JSON-serialized with type metadata.
- `origin` is an object and can be JSON-serialized with type metadata.

On receipt, the mapper can restore the object type based on the metadata and matching Jackson/type mapping configuration.

One thing to watch out for is that Java type metadata can couple consumers to the producer's class/package names. If the producer changes packages or the consumer lacks the matching class, restoring the object can fail even when the JSON payload itself is valid.

For cross-service events, prefer headers with simple, stable wire formats such as String or `byte[]`. If complex metadata objects are needed, define a contract independent of a single service's internal classes.

## 5. SimpleKafkaHeaderMapper

`SimpleKafkaHeaderMapper` is suitable when the application only needs to map String and `byte[]` headers without JSON type metadata for arbitrary objects.

It is useful when:

- Exchanging simple metadata across multiple languages.
- Wanting explicit control over byte format.
- Avoiding consumer coupling to producer Java classes.
- Needing only correlation ID, trace context, event version, or content type as strings/bytes.

Example metadata values that can be used:

~~~java
Message<OrderCreated> message =
    MessageBuilder.withPayload(event)
        .setHeader("correlation-id", "req-8f31")
        .setHeader("event-version", "2")
        .setHeader("content-type", "application/json")
        .build();
~~~

If using a mapper that only supports String/`byte[]`, object headers like `ServiceOrigin` must be converted to a string or `byte[]` before sending. This is often the easiest choice for interoperating with producers/consumers written in other languages.

## 6. Comparing the two mappers

| Criterion | DefaultKafkaHeaderMapper | SimpleKafkaHeaderMapper |
| --- | --- | --- |
| String | Supported | Supported |
| byte[] | Supported | Supported |
| Other objects | Can JSON-serialize | Application must convert to String/byte[] |
| Type metadata | Can use `spring_json_header_types` | Does not use JSON type mapping mechanism |
| Interoperability | Must watch type metadata and classes | Simpler with explicit wire values |
| Use case | Spring-to-Spring with object headers | Simple headers, cross-language |

Neither mapper is best for every case. If headers are just standard string or byte metadata, `SimpleKafkaHeaderMapper` keeps the wire format explicit. If the application needs to pass object headers between Spring components and accepts type metadata, `DefaultKafkaHeaderMapper` is more convenient.

## 7. Mapping patterns: choosing which headers are transferred

Not every Spring Message header should be sent to Kafka. `MessageHeaders` can contain internal framework metadata such as ID and timestamp, whereas a Kafka record should only carry metadata needed by consumers.

`DefaultKafkaHeaderMapper` supports patterns to select headers by name. Patterns can use wildcards and the negation prefix `!` to exclude headers. Patterns are evaluated in the order configured; the first matching pattern decides whether a header is mapped or excluded. Therefore, place specific exclusions before a general wildcard like `*`.

Example configuration transferring only business and trace headers:

~~~java
@Bean
public KafkaHeaderMapper kafkaHeaderMapper() {
    return new DefaultKafkaHeaderMapper(
        "!id",
        "!timestamp",
        "correlation-id",
        "event-*",
        "traceparent",
        "tracestate"
    );
}
~~~

The example above excludes internal ID/timestamp and allows only the listed headers. Concrete pattern names should match your application's naming convention.

If you want to map all headers except specific internal ones, you can combine negative patterns with a wildcard:

~~~java
@Bean
public KafkaHeaderMapper kafkaHeaderMapper() {
    return new DefaultKafkaHeaderMapper(
        "!id",
        "!timestamp",
        "*"
    );
}
~~~

Do not use a broad wildcard if messages may carry a security context, authentication object, or internal metadata not meant for consumers. A business-based allowlist is usually easier to review and safer.

## 8. Raw header mapping and encoding

For some headers, the application wants exact byte-level control rather than JSON-serializing objects. For instance, `traceparent`, `correlation-id`, and `event-version` typically have UTF-8 wire values.

`DefaultKafkaHeaderMapper` supports configuring headers to be mapped raw via APIs such as `addRawMappedHeader` or `setRawMappedHeaders` depending on the version. Raw mapping is helpful when reading/writing headers as strings or bytes without going through JSON type metadata.

Guidelines when choosing raw mapping:

- Agree on a charset, typically UTF-8 for text.
- Clearly specify whether a header is text or binary.
- Do not serialize the same header in two different formats across producers.
- Verify inbound/outbound behavior of raw settings for your Spring Kafka version.
- Include tests confirming sent bytes match what the consumer receives.

Example manually creating a raw Kafka header without relying on a mapper:

~~~java
ProducerRecord<String, OrderCreated> record =
    new ProducerRecord<>("order-events", event.orderId(), event);

record.headers().add(
    "correlation-id",
    "req-8f31".getBytes(StandardCharsets.UTF_8)
);

kafkaTemplate.send(record);
~~~

Here the application writes directly to Kafka Headers, so no mapper is needed to transfer that header. This is appropriate when exact control over the byte wire format is needed.

## 9. Attaching HeaderMapper to the message converter

`MessagingMessageConverter` converts between Kafka records and Spring Messages. It handles payload conversion and uses `KafkaHeaderMapper` to convert header metadata.

The mapper can be attached to the converter:

~~~java
@Bean
public RecordMessageConverter kafkaRecordMessageConverter(
        KafkaHeaderMapper kafkaHeaderMapper) {

    MessagingMessageConverter converter =
        new MessagingMessageConverter();

    converter.setHeaderMapper(kafkaHeaderMapper);
    return converter;
}
~~~

For the listener container factory, you can configure the record converter:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        orderKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory,
            RecordMessageConverter kafkaRecordMessageConverter) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setRecordMessageConverter(kafkaRecordMessageConverter);
    return factory;
}
~~~

For `KafkaTemplate`, you can set the corresponding message converter when using the Spring Message send API:

~~~java
@Bean
public KafkaTemplate<String, OrderCreated> orderKafkaTemplate(
        ProducerFactory<String, OrderCreated> producerFactory,
        RecordMessageConverter kafkaRecordMessageConverter) {

    KafkaTemplate<String, OrderCreated> template =
        new KafkaTemplate<>(producerFactory);

    template.setMessageConverter(kafkaRecordMessageConverter);
    return template;
}
~~~

API names and auto-configuration behavior may vary across Spring Kafka/Spring Boot versions. If the application uses default factories, verify which converter is actually attached to the template and listener container; merely declaring a mapper bean does not guarantee every converter uses it in all setups.

## 10. Sending a Spring Message with custom headers

When using `KafkaTemplate` with a message converter, you can build a Spring Message via `MessageBuilder`:

~~~java
Message<OrderCreated> message =
    MessageBuilder.withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, "order-events")
        .setHeader(KafkaHeaders.MESSAGE_KEY, event.orderId())
        .setHeader("correlation-id", "req-8f31")
        .setHeader("event-version", "2")
        .setHeader("content-type", "application/json")
        .build();

kafkaTemplate.send(message);
~~~

The message converter extracts topic/key from Spring Kafka's dedicated headers and converts custom headers through `KafkaHeaderMapper`. System headers like `KafkaHeaders.TOPIC` and `KafkaHeaders.MESSAGE_KEY` control template routing; they are not custom metadata to be mapped manually like correlation ID.

If calling `KafkaTemplate.send(topic, key, value)` directly, the application can construct a `ProducerRecord` to add native Kafka headers or use the `Message` send API with a converter. Pick one consistent approach to avoid mixing up send-control headers and business headers.

## 11. Reading custom headers in @KafkaListener

A listener can accept the full `ConsumerRecord` to access Kafka Headers:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "billing-service"
)
public void onOrderEvent(
        ConsumerRecord<String, OrderCreated> record) {

    Header header =
        record.headers().lastHeader("correlation-id");

    String correlationId = header == null
        ? null
        : new String(header.value(), StandardCharsets.UTF_8);

    billingService.process(record.value(), correlationId);
}
~~~

This approach lets you read headers in byte form and retains access to duplicate headers.

If the listener only needs a few metadata values, you can bind them with `@Header`:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "billing-service"
)
public void onOrderEvent(
        OrderCreated event,
        @Header(name = "correlation-id", required = false)
        String correlationId,
        @Header(name = "event-version", required = false)
        String eventVersion) {

    billingService.process(event, correlationId, eventVersion);
}
~~~

Binding a `String` depends on the message converter and header mapper having converted bytes into the expected type. If the header is kept as `byte[]`, the listener parameter must use the corresponding type or decode it manually.

You can receive all Spring Message headers using `@Headers Map<String, Object>` when the listener uses message conversion. This is convenient for general metadata handling, but it does not preserve multiple duplicate-named headers like Kafka Headers do.

## 12. Spring Kafka system headers

Spring Kafka uses several dedicated headers to pass metadata between Kafka records and listener methods. Examples:

| Header | Meaning |
| --- | --- |
| `KafkaHeaders.TOPIC` | Target topic when sending a message. |
| `KafkaHeaders.MESSAGE_KEY` | Record key when sending via the Message API. |
| `KafkaHeaders.PARTITION` | Explicitly specified partition when sending. |
| `KafkaHeaders.RECEIVED_TOPIC` | Topic of the record received by the consumer. |
| `KafkaHeaders.RECEIVED_PARTITION` | Partition of the received record. |
| `KafkaHeaders.OFFSET` | Offset of the received record. |
| `KafkaHeaders.RECEIVED_KEY` | Key of the received record. |
| `KafkaHeaders.RECEIVED_TIMESTAMP` | Timestamp of the received record. |

Constant names and value types can differ slightly across Spring Kafka generations. Prefer using constants rather than hard-coding string names when accessing framework headers.

Do not define custom headers with the same names as framework headers. Some headers only have meaning during Spring Message conversion and are not necessarily written verbatim into the Kafka record.

## 13. Duplicate headers and header ordering

Kafka allows a record to have multiple headers with the same name. For example:

~~~java
record.headers().add("tag", "priority".getBytes(StandardCharsets.UTF_8));
record.headers().add("tag", "customer".getBytes(StandardCharsets.UTF_8));
~~~

Reading all values:

~~~java
for (Header header : record.headers().headers("tag")) {
    String value =
        new String(header.value(), StandardCharsets.UTF_8);
    log.info("tag={}", value);
}
~~~

`lastHeader("tag")` retrieves only the last header with that name. If business logic needs every tag, iterate over the collection instead of reading only `lastHeader`.

When converting to `MessageHeaders`, a map cannot directly represent multiple values for the same key. If duplicate headers are part of the contract, keep `ConsumerRecord` or establish a convention to aggregate them into a `List<String>` in a custom mapper/converter.

## 14. Header mapping across languages and services

Kafka is often the integration backbone for services written in Java, Go, Python, Node.js, or .NET. Headers should use simple wire formats so every client can read them.

A header contract might specify:

| Header | Wire format | Rule |
| --- | --- | --- |
| `correlation-id` | UTF-8 string | ID of the request/event flow. |
| `event-type` | UTF-8 string | Stable event name, not a Java class name. |
| `event-version` | UTF-8 string or text-encoded number | Contract version. |
| `content-type` | UTF-8 string | MIME type of the payload. |
| `traceparent` | W3C Trace Context string | Standard trace context. |
| `source-service` | UTF-8 string | Name of the emitting service. |

Do not send arbitrary Java objects in headers if multi-language consumers need to read them. A JSON mapper can serialize objects, but that does not mean Go/Python consumers understand Java type metadata or Spring's special type headers.

If object metadata is required, define a small JSON schema and store the JSON bytes in the header, or move that data into a payload envelope when it carries significant business meaning.

## 15. Security and header size limits

Headers are stored alongside the record and can be accessed by any consumer authorized to read the topic. Therefore:

- Do not put passwords, access tokens, or secrets into headers.
- Do not treat headers as a separate security channel from the payload.
- Keep metadata small and essential.
- Avoid putting large business payloads into headers.
- Do not allow all internal headers to pass automatically through the mapper.
- Control type metadata if using `DefaultKafkaHeaderMapper`.
- Do not log all headers if they may contain sensitive information.

Headers contribute to record/batch size and are subject to Kafka/broker/client message size limits. Many large headers increase network, memory, and processing costs. The main payload should reside in the value; headers should carry only supporting metadata.

## 16. Testing header mapping

Test mapping in both directions and verify the actual wire format.

### 16.1. Outbound mapper tests

Create a Spring Message with String, `byte[]`, and object headers, then invoke the mapper to convert to Kafka Headers. Verify:

- Allowlisted headers are transferred.
- Excluded headers do not appear.
- String/`byte[]` preserve their exact values.
- Object headers are serialized according to the chosen policy.
- Type metadata appears only when configuration requires it.

### 16.2. Inbound mapper tests

Create Kafka Headers with byte values and map them to Spring headers. Verify:

- Expected headers are restored.
- Charset decoding is accurate.
- Disallowed headers do not appear.
- Type metadata is handled properly.
- Duplicate headers are handled according to the defined contract.

### 16.3. Integration tests with Kafka

Use Embedded Kafka or Testcontainers to send records with custom headers and receive them via `@KafkaListener`. Verify topic, partition, offset, payload, and metadata. This test confirms the converter, mapper, and Kafka client are actually wired properly in the application context.

If the system has multi-language producers, use byte header fixtures generated by another client and verify the Spring consumer reads them properly; also check that headers produced by the Spring producer can be understood by the other client.

## 17. Common header mapping pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Header does not reach consumer | Pattern does not match or converter does not use expected mapper | Check mapper, converter, and allowlist patterns |
| Object header turned into JSON bytes | `DefaultKafkaHeaderMapper` serializes object types as JSON | Use String/`byte[]` or configure raw mapping |
| Consumer cannot restore header type | Missing type metadata, missing class, or wrong type mapping | Use a neutral contract, type mapping, or raw headers |
| String header arrives as `byte[]` | Mapper keeps raw bytes or converter does not decode as expected | Configure raw mapping/charset and verify parameter type |
| Some duplicate-named headers are lost | Spring `MessageHeaders` is a map and cannot hold duplicate keys | Read `ConsumerRecord.headers()` or aggregate into a collection |
| `id`/`timestamp` headers appear unexpectedly | Mapping pattern allows framework-generated headers | Exclude internal headers via patterns |
| Custom header overwrites system header | Name collision with `KafkaHeaders` | Use a dedicated custom namespace and Spring constants |
| Headers bloat record size | Sending large metadata or repeating headers | Keep headers small, move payload into value |
| Other service cannot read type metadata | Coupling to Spring's special Java type headers | Use neutral String/`byte[]` wire values |

## 18. HeaderMapper design checklist

Before releasing an event flow, confirm:

1. Which headers are business metadata, and which are internal framework metadata?
2. Are header names stable and following a consistent naming convention?
3. Are header values Strings, `byte[]`, or JSON objects?
4. Do you need `DefaultKafkaHeaderMapper` or `SimpleKafkaHeaderMapper`?
5. Do mapping patterns exclude `id`/`timestamp` and sensitive headers?
6. Does type metadata create class/package coupling between producer and consumer?
7. Does raw mapping clearly specify charset and wire format?
8. Are the converters on `KafkaTemplate` and the listener container using the intended mapper?
9. Do duplicate headers need to be preserved or mapped into Spring `MessageHeaders`?
10. Are headers small, free of secrets, and non-conflicting with system header names?
11. Are there inbound/outbound unit tests and integration tests with a broker?
12. Can multi-language consumers understand the wire format sent by the producer?

`KafkaHeaderMapper` helps Spring Kafka transfer metadata between Kafka Headers and Spring `MessageHeaders`. `DefaultKafkaHeaderMapper` fits when mapping object headers via JSON and type metadata; `SimpleKafkaHeaderMapper` fits simple String/`byte[]` headers for easy cross-language interoperability. By intentionally choosing mapping patterns, raw formats, and converters, applications can propagate correlation, trace, and event metadata reliably without turning headers into a dependency on internal classes or a place for large payloads.


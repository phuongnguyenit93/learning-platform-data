# The `contentType`, `id`, and `timestamp` Headers

In Spring Cloud Stream, a message contains more than just a payload. It also carries headers that describe how to interpret the payload and provide metadata for processing. Three commonly encountered headers are `contentType`, `id`, and `timestamp`. Understanding their roles accurately helps producers and consumers agree on data formats, track a message during processing, and distinguish when a message was constructed from when the business event actually occurred.

`contentType` describes the content type so the framework can choose how to convert the payload. `id` identifies a message instance in the Spring Messaging model. `timestamp` records when the message was created according to Spring metadata. Both `id` and `timestamp` are framework-managed headers; they do not replace a stable business event identifier such as `eventId` or a business occurrence timestamp such as `occurredAt`.

## 1. Message Structure in Spring

Spring Messaging represents a message with a payload and headers:

```java
public record OrderItem(String productId, int quantity) {}

public record OrderCreated(
        String eventId,
        String orderId,
        BigDecimal total,
        Instant occurredAt,
        List<OrderItem> items) {}

public record OrderValidated(String eventId, String orderId, BigDecimal total) {}

OrderCreated orderCreated = new OrderCreated(
        "evt-001", "ord-100", new BigDecimal("29.90"), Instant.now(), List.of());

Message<OrderCreated> message = MessageBuilder
        .withPayload(orderCreated)
        .setHeader("eventId", orderCreated.eventId())
        .build();
```

- **Payload** is the main data processed by the consumer, such as `OrderCreated`.
- **Headers** are accompanying metadata, such as `contentType`, `id`, `timestamp`, `correlationId`, or a routing key.

In Spring, `Message<T>` provides `getPayload()` and `getHeaders()`. `MessageHeaders` is a read-only structure once the message is created. When you need to create a new message or change headers, use `MessageBuilder` to create a new message rather than modifying the existing message's header map directly.

```java
OrderCreated payload = message.getPayload();
MessageHeaders headers = message.getHeaders();

UUID messageId = headers.getId();
Long createdAtMillis = headers.getTimestamp();
Object contentType = headers.get(MessageHeaders.CONTENT_TYPE);
```

A message may pass through multiple components in an application. Each component should clearly know which data belongs in the payload and which metadata belongs in headers. Business fields that must be persisted and exchanged across multiple systems should normally reside in the payload schema or a standardized business header, rather than depending on internal metadata that only exists inside the JVM.

## 2. The `contentType` Header: Payload Format

`contentType` describes the media type of the payload, typically using MIME syntax. Spring Cloud Stream uses this information during message conversion between Java types and the data representation transported over the binder.

Some common values:

| Content type | Meaning | Payload example |
|---|---|---|
| `application/json` | JSON data | An order object serialized as JSON |
| `text/plain` | Plain text | An order ID or short notification |
| `application/octet-stream` | Binary data | A byte array or file contents |
| `application/avro` | Avro data | A record serialized according to an Avro schema and matching configuration |
| `application/x-protobuf` | Protocol Buffers data | A message serialized according to a Protobuf schema and matching configuration |

Content type does not automatically transform an arbitrary payload into the corresponding format. The framework needs an appropriate converter; for Avro or Protobuf, the application also needs the corresponding libraries and schema/serialization rules. Declaring the wrong content type can cause the consumer to select the wrong converter or fail to decode the data.

### 2.1. Declaring Content Type at the Binding

You can set a default content type per binding in `application.yml`:

```yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
          content-type: application/json
        processOrder-in-0:
          destination: orders
          group: inventory-service
          content-type: application/json
```

`publishOrder-out-0` is the output binding of the producer function; `processOrder-in-0` is the input binding of the consumer. Both sides must agree on the data contract. Declaring `content-type` makes converter selection explicit per binding and easy to manage across environment profiles.

Example of a producer emitting a JSON message:

```java
@Bean
Supplier<Message<OrderCreated>> publishOrder() {
    return () -> {
        OrderCreated event = new OrderCreated(
                UUID.randomUUID().toString(),
                "ord-100",
                new BigDecimal("29.90"),
                Instant.now(),
                List.of(new OrderItem("book-01", 2)));

        return MessageBuilder.withPayload(event)
                .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
                .setHeader("eventId", event.eventId())
                .setHeader("occurredAt", event.occurredAt().toString())
                .build();
    };
}
```

The `OrderCreated` definition here only illustrates the data structure. In a real application, the event ID should be generated where the event originates and remain stable across retries or replays. Do not generate a new event ID on each retry of the same event.

### 2.2. Setting Content Type Directly on the Message

When a binding needs to emit multiple content types or a function creates messages with specific metadata, you can attach the content type via `MessageBuilder`:

```java
Message<byte[]> binaryMessage = MessageBuilder
        .withPayload(serializedBytes)
        .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_OCTET_STREAM)
        .build();
```

`MessageHeaders.CONTENT_TYPE` is the standard Spring Messaging header name; `MimeTypeUtils` provides common MIME values. The header can be set with a `MimeType` or a compatible value supported by the converter/binder. For typical bindings, configuring content type at the binding level is easier to read and manage; setting it directly on the message is useful when per-message metadata is needed.

### 2.3. Content Type and Native Encoding

Spring Cloud Stream can perform payload conversion inside the framework or let the client/broker serializer handle it according to the binder's native encoding/decoding configuration. When native mode is enabled, the application must configure the serializer/deserializer and data types compatible with the broker. Simply setting the `contentType` header does not configure native serializers, schema registries, or schema compatibility rules.

Clearly define which side is responsible for serialization and deserialization. Do not have the producer serialize JSON into a string while declaring the payload as an unserialized object, or have the consumer both decode natively and ask the framework to convert again. Run round-trip tests through a real broker to confirm bytes are produced and read back according to the contract.

## 3. The `id` Header: Identifying a Message Instance

Spring Messaging provides the `id` metadata for a message. When building a message with `MessageBuilder`, Spring typically generates a UUID automatically if no valid ID is already retained in metadata. You can read the value with:

```java
UUID messageId = message.getHeaders().getId();
```

Spring's ID helps identify a message instance during in-application processing. The `id` and `timestamp` headers are framework-managed metadata; avoid trying to assign them as custom headers. The `id` header is not an order ID, transaction ID, or business event ID. When a new message is created during a transformation step, the new message may get a different ID. Therefore, do not use the Spring message ID as a long-term idempotency key or as a business identifier across multiple replays.

### 3.1. Distinguishing `id` and `eventId`

`eventId` is application-defined metadata to identify a business event. It should be generated once at the event source and remain stable when the message is retried, redelivered, or replayed. `id` is the message identifier in the Spring Messaging model.

| Attribute | `id` | `eventId` |
|---|---|---|
| Owner | Spring Messaging/framework | Application and event contract |
| Purpose | Identifies a message instance | Identifies a business event |
| Stability when creating a new message | May change | Must remain the same if it is still the same event |
| Used as idempotency key | Not recommended | Possible, if generated uniquely and stored/checked properly |
| Where declared | Framework-managed `id` header | Payload field or custom `eventId` header |

Example of a consumer using the event ID to prevent duplicate processing:

```java
@Bean
Consumer<Message<OrderCreated>> handleOrder() {
    return message -> {
        OrderCreated event = message.getPayload();
        String eventId = event.eventId();

        inventoryService.reserveOnce(eventId, event);
    };
}
```

`reserveOnce` must persist a processing marker using a unique constraint or an appropriate transaction in the data store. Checking only an in-memory collection or comparing Spring message IDs is insufficient for deduplication across multiple instances and restarts.

## 4. The `timestamp` Header: Message Creation Time

Spring Messaging provides `timestamp` to record when a message was created, typically represented as milliseconds since the Unix epoch (UTC). You can read the value with:

```java
Long timestampMillis = message.getHeaders().getTimestamp();
Instant messageCreatedAt = timestampMillis == null
        ? null
        : Instant.ofEpochMilli(timestampMillis);
```

When a message is built with `MessageBuilder`, Spring typically populates the timestamp automatically if the metadata does not already have a value. This is the message creation time in the Spring model; it is not necessarily when the business event occurred, when the producer wrote the record to the broker, or when the consumer received the message.

### 4.1. Distinguishing `timestamp` and `occurredAt`

An order might be created at 09:00 but only emitted as a message at 09:03 because the application had to wait for a transaction to complete. The consumer might receive the message at 09:04. These three timestamps have different meanings:

| Point in time | Meaning | Example |
|---|---|---|
| `occurredAt` | Business occurrence time, recorded by the domain event | Order created at 09:00 |
| Spring `timestamp` | Message creation time in the application | Producer built the message at 09:03 |
| Receive/ingest time | Time the broker or consumer observed the message | Consumer received at 09:04 |

If you need to analyze business latency, detect late-arriving events, or order by business time, include `occurredAt` in the payload or a custom header with a clear timezone convention. Prefer ISO-8601 UTC, such as `2026-11-24T02:00:00Z`, to avoid timezone ambiguity. If you need the time the broker received the record, use broker-provided metadata and understand that broker's semantics.

Do not use Spring `timestamp` in place of `occurredAt` in business reporting. The difference between event time and processing time is especially important for late-arriving data, prolonged retries, and time-windowed processing.

## 5. Creating Messages with Explicit Metadata

The following example receives a message, constructs a new result, and preserves the required business headers:

```java
@Bean
Function<Message<OrderCreated>, Message<OrderValidated>> validateOrder() {
    return input -> {
        OrderCreated event = input.getPayload();
        OrderValidated result = new OrderValidated(
                event.eventId(),
                event.orderId(),
                event.total());

        MessageBuilder<OrderValidated> builder = MessageBuilder
                .withPayload(result)
                .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
                .setHeader("eventId", event.eventId())
                .setHeader("occurredAt", event.occurredAt().toString());

        String correlationId = input.getHeaders().get("correlationId", String.class);
        if (correlationId != null) {
            builder.setHeader("correlationId", correlationId);
        }

        return builder.build();
    };
}
```

Here:

- The output payload has type `OrderValidated`, without mutating the input payload.
- `contentType` indicates that the output payload is JSON.
- `eventId` preserves the identifier of the original event if this is still the same event being transformed.
- `occurredAt` preserves the business timestamp, while Spring manages `id` and `timestamp` of the newly created message.
- `correlationId` is intentionally copied to link processing steps within the same business flow.

If the processing step produces a new business event, generate a new `eventId` for that event and consider keeping `correlationId` or adding `causationId` to trace its relationship to the source event. Do not blindly copy all headers: some headers may carry internal control, routing, or reply-channel information that only makes sense within the application's message channels.

## 6. Custom Headers and Broker Mapping Capabilities

Applications can define headers such as `eventId`, `correlationId`, `causationId`, `occurredAt`, `tenantId`, or `schemaVersion`. Before using them, the team should agree on their names, data types, meanings, origin, and retention rules as messages traverse multiple services.

Not every Spring header is transmitted across brokers in the same way. The binder must map Spring metadata to the broker's header/property structure and vice versa. Each broker has limits on data types, size, encoding, and header names:

| Broker | Broker-level metadata mechanism | What to verify |
|---|---|---|
| Kafka | Record headers, header values as byte arrays | The mapper converts Spring data types to bytes and restores the correct value when the consumer receives it |
| RabbitMQ | AMQP message properties and headers field table | Data types supported by AMQP, header names, and header mapper configuration |
| Pulsar | Message properties attached to the message | Data types and how the binder converts headers into properties, especially for non-string values |

Therefore, prefer simple header values such as strings, numbers, booleans, or byte arrays according to binder capabilities. Avoid putting arbitrary Java objects, large collections, or sensitive data into headers. A custom header may exist on an internal message yet be ignored, type-converted, or not preserved when crossing a broker if the binder does not support that mapping.

If a value has long-term significance to the consumer, consider placing it in the payload schema. Headers are better suited for control, routing, correlation, or content representation metadata. Whether you choose payload or headers, the contract must be documented and tested for compatibility.

## 7. Testing Headers in the Application

Metadata can be verified at the unit level without a broker:

```java
@Test
void messageContainsContentTypeAndFrameworkMetadata() {
    OrderCreated payload = sampleOrder();

    Message<OrderCreated> message = MessageBuilder.withPayload(payload)
            .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
            .setHeader("eventId", payload.eventId())
            .build();

    assertThat(message.getPayload()).isEqualTo(payload);
    assertThat(message.getHeaders().get(MessageHeaders.CONTENT_TYPE))
            .isEqualTo(MimeTypeUtils.APPLICATION_JSON);
    assertThat(message.getHeaders().getId()).isNotNull();
    assertThat(message.getHeaders().getTimestamp()).isNotNull();
    assertThat(message.getHeaders().get("eventId")).isEqualTo(payload.eventId());
}
```

Unit tests verify that the message is constructed properly inside the JVM. They do not prove that the binder transmitted all headers through Kafka, RabbitMQ, or Pulsar. Integration tests are needed to:

1. Publish a message with `contentType`, `eventId`, `correlationId`, and `occurredAt`.
2. Receive the message in the consumer via a real broker.
3. Verify the payload is deserialized with the right type and content.
4. Verify key custom headers retain their exact values and types.
5. Observe `id` and `timestamp` after the message passes through the binder, without assuming they are preserved identically across all brokers.
6. Test cases with unsupported headers, mismatched content types, or schema-incompatible payloads.

When debugging, you can log `eventId`, `correlationId`, `contentType`, message ID, and timestamp. Avoid logging entire payloads or headers containing tokens, credentials, and personal data. Logs should distinguish message ID from event ID so operations teams do not mistake a new message creation for a new business event.

## 8. Common Mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| Consumer fails to deserialize payload | `contentType` does not match actual format or converter is missing | Align content type, serializer, and converter between producer and consumer |
| JSON is received as a string or byte array | Binding/native encoding is configured differently than expected | Check content type and native encoding/decoding settings on both sides |
| `eventId` header missing at consumer | Binder does not map the header, header name differs, or header is filtered | Inspect header mapper and test over a real broker |
| Using `id` for deduplication still causes duplicate processing | New message has a different ID or broker redelivery does not preserve metadata as expected | Use a stable application-managed `eventId` and persist processing markers durably |
| Timestamp does not reflect business time | Reading message creation time instead of `occurredAt` | Add event time to payload or a custom header in UTC format |
| Header has a different type upon receipt | Broker/binder converted the value into a supported type | Standardize header types, such as ISO-8601 strings or numbers, and test the mapping |
| New message loses correlation ID | Output message function did not copy needed headers | Intentionally select and forward needed business/tracing headers |

## 9. Header Design Checklist Before Deployment

- [ ] `contentType` is explicitly declared on the binding or message and matches how the payload is serialized.
- [ ] Producer and consumer agree on schema, converter, or native serializer/deserializer.
- [ ] `id` is understood as Spring's message identifier and is not used as a long-term business key.
- [ ] `eventId` is stable across retries and replays; consumers use it for idempotency where appropriate.
- [ ] `timestamp` is understood as message creation metadata; event time is represented separately via `occurredAt`.
- [ ] `correlationId` and `causationId` follow clear conventions for tracing across multiple services.
- [ ] Custom headers have documented names, types, sizes, and meanings.
- [ ] Key headers are tested for mapping across the exact binder and broker used in deployment.
- [ ] No secrets or large payloads are placed in headers; internal control headers are not copied indiscriminately.

`contentType`, `id`, and `timestamp` help Spring Cloud Stream process and describe messages, but each header has its own scope. Content type assists in choosing how to convert the payload; ID identifies the message instance; timestamp records when the message was created. Applications still need to define event ID, event time, and correlation metadata according to the business contract, and test header mapping over a real broker to ensure consumers receive the exact data they need.

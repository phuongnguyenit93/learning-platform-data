# Handling Direct Payloads vs. Handling Message<T>

## Objectives

In Spring Cloud Stream's functional model, a function can directly receive a business object such as `OrderCreated`, or receive a `Message<OrderCreated>` containing both a payload and metadata. Both approaches are valid, but they serve different needs. Choosing the right function signature keeps code readable, preserves required broker information, and prevents messaging metadata from leaking into business logic.

This lesson explains the structure of `Message<T>`, how Spring Cloud Stream converts payloads according to target types and content types, how to read or construct headers, and how to choose between a direct payload and a full message when using `Supplier`, `Function`, and `Consumer`.

After this lesson, you will be able to:

- Distinguish between payload and headers in a Spring Message.
- Write Consumers and Functions that accept a direct payload or `Message<T>`.
- Read metadata such as event ID, correlation ID, and tenant ID at the integration boundary.
- Create output messages with selectively chosen headers.
- Configure content types and test payload/header conversion.

## 1. Payload and Message Are Two Different Things

Spring Messaging represents a message using two components:

- **Payload** is the primary data the application needs to process, such as a newly created order.
- **Headers** are accompanying metadata, such as content type, correlation ID, tenant ID, timestamp, or routing information.

The `Message<T>` type holds a payload of type `T` along with a set of headers:

```java
public record OrderCreated(
        String eventId,
        String orderId,
        BigDecimal total
) {}
```

A message can wrap this object along with headers:

```java
Message<OrderCreated> message = MessageBuilder
        .withPayload(new OrderCreated(
                "evt-100", "order-42", new BigDecimal("125.50")
        ))
        .setHeader("correlationId", "corr-900")
        .setHeader("tenantId", "tenant-a")
        .build();
```

In this example, `OrderCreated` is the payload. `correlationId` and `tenantId` are metadata. Some metadata, such as content type, can affect data conversion; other headers are purely for observability, tracing, or routing.

`Message<T>` is a Spring Messaging abstraction. It is not a verbatim copy of a Kafka, RabbitMQ, or Pulsar record. The binder translates between framework messages and the broker's protocol, and may map or normalize headers according to the binder's capabilities.

## 2. Receiving the Payload Directly

When business logic only needs data inside the payload, declare the function to accept the payload type:

```java
@Bean
Consumer<OrderCreated> orderCreated(OrderService service) {
    return event -> service.createOrder(
            event.orderId(),
            event.total()
    );
}
```

This is the simplest and usually preferred form. Spring Cloud Stream receives the message from the binding, converts the payload into `OrderCreated` based on the content type and function parameter type, and invokes the Consumer. Handler code does not need to call `getPayload()` everywhere.

A Function can also accept and return payloads directly:

```java
@Bean
Function<OrderCreated, OrderAccepted> acceptOrder(OrderService service) {
    return event -> service.accept(event);
}
```

With a Supplier, the application produces the output data:

```java
@Bean
Supplier<Heartbeat> heartbeat() {
    return () -> new Heartbeat("inventory-service", Instant.now());
}
```

When using direct payloads, the framework manages the message envelope and conversion process. This approach fits when:

- The logic only needs fields from the payload.
- There is no need to read delivery metadata.
- The output can be represented by a clear business object or DTO.
- You want to keep function signatures concise and easy to test.

Avoid stuffing headers into the payload solely to replace message metadata. For instance, correlation IDs or routing details are usually not part of the `OrderCreated` business contract.

## 3. Receiving Message<T> When Metadata Is Needed

When processing requires both payload and metadata, declare the parameter as `Message<T>`:

```java
@Bean
Consumer<Message<OrderCreated>> orderCreated(
        OrderService service) {
    return message -> {
        OrderCreated event = message.getPayload();

        String correlationId = message.getHeaders()
                .get("correlationId", String.class);

        service.createOrder(
                event.orderId(),
                event.total(),
                correlationId
        );
    };
}
```

The generic type `Message<OrderCreated>` keeps the payload strongly typed. The application can access:

- `message.getPayload()` to obtain the primary data.
- `message.getHeaders()` to read metadata.
- `message.getHeaders().get(key, Type.class)` to retrieve a header in the expected type.

If a header is optional, handle the missing case explicitly:

```java
String correlationId = message.getHeaders()
        .get("correlationId", String.class);

if (correlationId == null || correlationId.isBlank()) {
    correlationId = "untracked";
}
```

Default values are only appropriate when business logic and observability allow them. If a header is mandatory—such as a tenant ID used to scope data—the adapter must reject missing or invalid values before invoking the use case. Never apply a generic fallback value that could route a message into the wrong tenant.

### Message<T> Still Converts the Payload

Using `Message<OrderCreated>` does not mean the payload remains a raw byte array or JSON string. Spring Cloud Stream can still convert the payload into `OrderCreated` based on content type information and the function signature. The difference is that the function receives the entire envelope so it can inspect metadata.

Prefer concrete generic types:

```java
Consumer<Message<OrderCreated>> typedHandler = message -> {
    OrderCreated event = message.getPayload();
};
```

Avoid using `Message<?>` or `Message<Object>` unless you genuinely need to handle multiple payload types. Overly broad types reduce target type information for conversion and force runtime casting or type checks.

## 4. Creating Output Messages and Selecting Headers to Propagate

A Function can accept `Message<T>` and return `Message<R>`. This is useful when certain metadata must be preserved across processing:

```java
@Bean
Function<Message<OrderCreated>, Message<OrderAccepted>> acceptOrder(
        OrderService service) {
    return input -> {
        OrderCreated event = input.getPayload();
        OrderAccepted accepted = service.accept(event);

        String correlationId = input.getHeaders()
                .get("correlationId", String.class);

        return MessageBuilder
                .withPayload(accepted)
                .setHeader("correlationId", correlationId)
                .setHeader("eventId", event.eventId())
                .build();
    };
}
```

The Function returns a new message with the output payload and a select set of headers. This makes it explicit which metadata is allowed to propagate forward.

You can use `MessageBuilder.fromMessage(input)` to construct a message based on the incoming message:

```java
Message<OrderAccepted> output = MessageBuilder
        .fromMessage(input)
        .setPayload(accepted)
        .setHeader("processingStage", "validated")
        .build();
```

This approach retains existing headers unless they are overwritten or removed. Only use it when preserving those headers is intentional. Incoming messages can contain broker- or framework-specific metadata; copying everything onto the output message may leak internal details, carry stale contextual headers, or cause conflicts when sending through another binder.

In many cases, building a new message with `MessageBuilder.withPayload(...)` and setting only an allowlist of headers is easier to control. For example, correlation ID, event ID, and trace context can be forwarded if system policy permits.

### Output Messages from a Supplier

A Supplier can also create a message when the source needs to attach metadata:

```java
@Bean
Supplier<Message<Heartbeat>> heartbeat() {
    return () -> MessageBuilder
            .withPayload(new Heartbeat("inventory-service", Instant.now()))
            .setHeader("eventType", "service.heartbeat")
            .build();
}
```

The payload remains the heartbeat data; `eventType` is metadata. If a header is part of an inter-service contract, document its name, type, and compatibility rules, and verify that the binder maps that header to the broker as expected.

## 5. Choosing Payload vs. Message<T>

| Need | Recommended Signature | Reason |
|---|---|---|
| Process only business data | `Consumer<OrderCreated>` | Concise, decoupled from envelope |
| Need correlation ID or tenant metadata | `Consumer<Message<OrderCreated>>` | Reads payload and headers at boundary |
| Transform payload without preserving metadata | `Function<OrderCreated, OrderAccepted>` | Focuses on input/output data |
| Transform payload and selectively forward headers | `Function<Message<OrderCreated>, Message<OrderAccepted>>` | Controls output metadata |
| Emit periodic data without metadata | `Supplier<Heartbeat>` | Simple declaration |
| Source needs to attach event type or correlation metadata | `Supplier<Message<Heartbeat>>` | Produces both payload and headers |

A practical rule: start with the direct payload. Switch to `Message<T>` when there is a concrete requirement for metadata or when you need to control the output envelope. Do not choose `Message<T>` simply because it looks more general.

## 6. Headers: Conventions, Trustworthiness, and Compatibility

Headers are useful, but they are also a boundary that must be managed.

### Distinguishing Business Headers from Transport Headers

Certain headers often carry cross-service meaning:

- `eventId`: a stable event identifier for deduplication.
- `correlationId`: links messages belonging to the same processing flow.
- `traceparent`: trace context information following the W3C Trace Context standard, if the system uses this standard.
- `tenantId`: tenant identifier when the architecture requires tenant-scoped routing or validation.

Other headers are tied to the protocol or binder—for example, partition, offset, delivery tag, routing key, or subscription metadata. These headers are useful for adapters and operations, but should not be placed directly into the domain model.

The same concept may be represented differently across brokers. Kafka has record headers and partition/offset metadata; RabbitMQ has properties, headers, and routing keys; Pulsar has properties and message metadata. The binder is responsible for mapping supported values. Do not assume every custom header or broker-specific header automatically traverses every binder or preserves its data type.

### Do Not Treat Headers as Trusted Data

Headers coming from external systems must be validated just like payloads:

- Validate types and formats.
- Verify whether the tenant ID is authorized for access.
- Constrain lengths and accepted value sets.
- Never use producer-supplied headers as proof of authentication or authorization.
- Never write tokens, passwords, or secrets into headers.

If tenant information is needed for database access, the adapter must validate the metadata through the system's trusted mechanism and pass a verified value into the application command/context.

### Framework-Managed Headers

Spring Messaging may attach metadata such as message ID and timestamp. Brokers/binders may also add delivery metadata. Do not use a framework-generated message ID in place of a stable business event ID: when a message is reconstructed or resent, the message ID may change while the event ID must stay the same.

Headers are a metadata structure, not a place to store full business data. If a field needs long-term persistence, validation as part of the business contract, or event reconstruction, consider placing that field inside the payload.

## 7. Content Type and Payload Conversion

When a message travels through a broker, the payload is usually serialized into bytes. Upon receipt, Spring Cloud Stream needs to know how to convert those bytes into the Java type expected by the function.

Content type describes the payload format, for example:

- `application/json` for JSON.
- `text/plain` for plain text content.
- A custom media type if the system uses a specialized event format.

Content type can be declared on the binding:

```yaml
spring:
  cloud:
    function:
      definition: orderCreated
    stream:
      bindings:
        orderCreated-in-0:
          destination: orders.created
          group: order-service
          content-type: application/json
```

With `Consumer<OrderCreated>`, the framework uses the parameter type and content type to pick the appropriate conversion mechanism. With `Consumer<Message<OrderCreated>>`, the payload can still be converted into `OrderCreated`; the message simply lets you read headers as well.

Several guidelines:

1. Producers and consumers must agree on schema and content type.
2. Specify content type explicitly when the contract cannot be safely inferred from defaults.
3. Do not cast payloads from `Object` when you can declare a concrete type directly in the function signature.
4. Handle conversion errors separately from business errors: an unparseable payload might never reach the function handler.
5. Test both real JSON and headers after passing through the binder.

Example JSON payload:

```json
{
  "eventId": "evt-100",
  "orderId": "order-42",
  "total": 125.50
}
```

The resulting `OrderCreated` object depends on the DTO and converter configuration. If the schema changes incompatibly, an error can occur during conversion before code inside the Consumer is ever called. Therefore, boundary logs and metrics should distinguish deserialization failures, header validation failures, and use-case failures.

## 8. Header Mapping and Differences Across Kafka, RabbitMQ, and Pulsar

Spring Cloud Stream provides a shared abstraction, but how headers map to brokers differs:

| Broker | Message-Attached Data | What to Check |
|---|---|---|
| Kafka | Record headers, key, partition, offset, and timestamp | How custom headers are serialized/deserialized; partition/offset are record metadata rather than payload |
| RabbitMQ | Message properties, headers, routing key, exchange, and delivery metadata | Header value types supported by broker/client; routing key is not synonymous with a custom header |
| Pulsar | Message properties, key, event time, and subscription metadata | Which headers/properties the binder maps; key and subscription metadata have distinct roles |

When switching binders, verify at least the headers your application uses: names, data types, propagation across the broker, overwrite rules, and behavior when a header is missing. An application can use the same `Message<T>` at the Spring level while receiving different sets of metadata from each binder.

Do not depend on broker-specific headers inside use cases. If a use case genuinely needs a value such as a partition key to decide distribution, consider turning it into an explicit port or policy at the application boundary; avoid reading technical headers directly inside domain entities.

## 9. Errors, Retries, and Acknowledgments Are Not Inside the Payload

Using `Message<T>` does not automatically alter delivery guarantees. Messages still pass through bindings and binders, so retries, acks, offset commits, transactions, and DLQs depend on configuration and the broker.

Distinguish between:

- **Conversion errors:** the framework cannot convert the payload into the target type. The function may not have been invoked.
- **Header validation errors:** the adapter received the message, but metadata is invalid; reject or route to the error-handling flow according to policy.
- **Business errors:** the use case cannot complete, such as an invalid order.
- **Infrastructure errors:** the database or broker is temporarily unavailable.

Do not catch an exception and return normally just to avoid retries when business work is unfinished. Normal function completion is generally treated by the framework/binder as successful processing according to configuration; swallowing errors can cause a message to be acknowledged while its data remains unprocessed.

Some binders expose specialized metadata or headers to control manual acknowledgment. Only use them when there is an explicit requirement and follow your binder version's documentation; never leak acknowledgment objects or delivery tags into domain/application layers. `Message<T>` is not a manual acknowledgment mechanism and does not create exactly-once semantics.

For incoming messages that may be redelivered, use a stable event ID and idempotent processing. If publishing new messages from a database change, consider the transactional outbox pattern to avoid gaps between database commits and broker sends.

## 10. Testing Payloads and Headers

Testing can be organized into three layers.

### Unit Tests for Business Logic

If a use case only accepts a command or payload, unit tests do not need to construct a Spring Message. This keeps tests focused on business rules.

### Unit Tests for Adapters Receiving Message<T>

Use `GenericMessage` to construct a payload alongside headers:

```java
@Test
void shouldPassPayloadAndCorrelationIdToUseCase() {
    var event = new OrderCreated(
            "evt-100", "order-42", new BigDecimal("125.50")
    );

    Message<OrderCreated> message = new GenericMessage<>(
            event,
            Map.of("correlationId", "corr-900")
    );

    var captured = new AtomicReference<String>();

    Consumer<Message<OrderCreated>> handler = input -> {
        String correlationId = input.getHeaders()
                .get("correlationId", String.class);
        captured.set(correlationId);
    };

    handler.accept(message);

    assertEquals("corr-900", captured.get());
}
```

This test verifies that adapter code reads the header properly. In use-case tests, verify the validated command or data passed in; do not force domain tests to construct a `Message`.

### Integration Tests Through the Binder

Use the Spring Cloud Stream Test Binder to verify binding flows at the framework level, or Testcontainers with the corresponding broker to verify real behavior. You should check:

- JSON converts to the expected payload type.
- `Message<T>` receives the expected application headers.
- Output headers are mapped and transmitted through the broker.
- Invalid headers are handled according to policy.
- Conversion errors and handler errors produce the expected retry/DLQ outcomes.
- When switching binders, critical headers retain the same semantics and data types.

The Test Binder is useful for testing code against Spring Cloud Stream abstractions, but it does not fully simulate all header mapping, serialization, and metadata rules specific to Kafka, RabbitMQ, or Pulsar. Broker-level guarantees must be tested against the target binder/broker.

## 11. Guidelines for Choosing Function Signatures in a Project

Before declaring a function bean, ask yourself:

1. Does the function need message metadata? If not, accept the payload directly.
2. Which metadata is genuinely needed by the use case? Forward only validated values with business meaning.
3. Does the function produce output messages with custom headers? If so, return `Message<R>` and build headers using an allowlist.
4. Does the payload have a concrete type? Prefer `Message<DomainEventDto>` over `Message<?>`.
5. Are the headers supported across all target binders? Check header mapping and write integration tests.
6. Which values must survive after the message is stored or replayed? Place durable data in the payload or business data store, rather than relying solely on transient metadata.

For Spring Cloud Stream applications supporting Kafka, RabbitMQ, or Pulsar, keeping DTOs and mapping at the adapter layer allows broker contracts to evolve without coupling use cases to messaging APIs. Use direct payloads for simple flows; use `Message<T>` where metadata must be read or produced.

## Conclusion

The payload holds the core event data; headers carry accompanying metadata. Spring Cloud Stream can convert payloads into Java types in both `T` and `Message<T>` signatures. Direct-payload signatures fit most straightforward business processing; `Message<T>` fits when the adapter needs to read metadata or control output headers.

Keep headers at the integration boundary, validate externally supplied values, and propagate only necessary metadata. Content types, header mapping, retries, and acknowledgments also depend on the specific binder. Test against the target broker to verify that messages preserve payloads and metadata when deployed with Kafka, RabbitMQ, or Pulsar.

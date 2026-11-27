# Business Headers and Event Versioning Information

In an event-driven system, the payload describes the event data, while headers provide metadata for identification, routing, tracing, and message interpretation. Some metadata belongs to infrastructure such as message ID or content type; other metadata carries application context such as tenant, correlation ID, or priority. When multiple services exchange events, they must agree on the meaning and data types of headers, as well as clearly define the event contract version.

Spring Cloud Stream allows a function to receive the full `Message<T>` to read both the payload and `MessageHeaders`, then build an output message using `MessageBuilder`. The binder transfers the message over Kafka, RabbitMQ, Pulsar, or another broker. Because header mapping depends on the transport and binder, event contracts must be designed intentionally so consumers still interpret data accurately as messages traverse multiple services.

## 1. Distinguishing Payload and Headers

The payload contains the business event: what happened, which entity was affected, and the facts needed by the consumer to process it. For example, `OrderPlaced` might contain the order ID, customer, total amount, and placement timestamp.

Headers are metadata attached to the message. They can help consumers identify the event type, trace a processing flow, apply routing rules, or choose how to decode the payload.

Example:

```java
public record OrderPlaced(
    String orderId,
    String customerId,
    BigDecimal total,
    Instant placedAt,
    String eventId
) {}
```

The payload above describes an order-placed event. A message might carry additional headers such as:

| Header | Meaning | Category |
|---|---|---|
| `eventType` | Event contract name, e.g., `com.example.orders.OrderPlaced` | Application contract |
| `eventVersion` | Schema or contract version of the event | Application contract |
| `eventId` | Unique ID of the event, used for auditing or deduplication | Application contract |
| `correlationId` | Links messages belonging to the same business flow | Tracing |
| `causationId` | ID of the event or message that directly caused the current event | Tracing |
| `tenantId` | Tenant context in a multi-tenant system | Business context |
| `contentType` | Payload format for conversion, e.g., JSON | Conversion |
| `id`, `timestamp` | Standard metadata managed by Spring Messaging | Framework |

Not every header is a "business header". Categorize metadata by purpose to avoid confusing business information, tracing metadata, and broker-specific details.

A useful principle is that core facts answering "what happened?" belong in the event payload. Headers should contain context that assists transport, routing, or observability of the message. For example, an order's total amount is a business fact and belongs in the payload; `correlationId` is tracing metadata and typically belongs in headers.

## 2. Designing Contract-Backed Business Headers

Custom headers are part of the integration contract if consumers rely on them for processing. Therefore, specify clearly:

- Stable header names with consistent casing that do not change arbitrarily.
- Clearly defined data types, e.g., `tenantId` is a string, `eventVersion` is an integer.
- The meaning, origin, and applicability scope of each header.
- Which headers are required, which are optional, and default values if missing.
- Which headers are permitted across the broker and which exist only internally within the application.
- Policies for validating, normalizing, and rejecting invalid headers.

For example, `tenantId` must be obtained from a trusted authentication context or from an authenticated producer. A consumer should never treat a tenant value sent by an arbitrary message as proof of authorization. Similarly, a `priority` header is only effective if the producer, binder, and broker share explicit handling rules.

Do not place passwords, access tokens, sensitive personally identifiable information, or secrets into headers. Headers are often logged, displayed in broker management tools, or forwarded through multiple intermediaries. Transmit only the minimum data necessary.

### Creating Messages with Custom Headers

Spring Messaging provides `MessageBuilder` for constructing messages:

```java
OrderPlaced event = new OrderPlaced(
    "order-1007",
    "customer-42",
    new BigDecimal("1250000"),
    Instant.now(),
    UUID.randomUUID().toString()
);

Message<OrderPlaced> message = MessageBuilder
    .withPayload(event)
    .setHeader("eventType", "com.example.orders.OrderPlaced")
    .setHeader("eventVersion", 1)
    .setHeader("eventId", event.eventId())
    .setHeader("correlationId", "checkout-9001")
    .setHeader("tenantId", "retail-vn")
    .build();
```

This example illustrates creating a message at the Spring Messaging level. When sending via Spring Cloud Stream, a function can return this message so the binder publishes it to the output binding. In a real system, event ID and correlation ID should come from the event creation context rather than hardcoded values.
If `eventId` also appears inside the payload/envelope, the header value must be copied from the exact same ID, rather than generating a different ID.

### Reading Headers in a Function

When a consumer needs both payload and metadata, declare its input type as `Message<T>`:

```java
@Bean
Consumer<Message<OrderPlaced>> processOrder(
        OrderApplicationService service) {

    return message -> {
        OrderPlaced event = message.getPayload();

        String eventId = (String) message.getHeaders().get("eventId");
        String tenantId = (String) message.getHeaders().get("tenantId");

        if (eventId == null || tenantId == null) {
            throw new InvalidEventMetadataException(
                "eventId and tenantId are required"
            );
        }

        service.process(event, eventId, tenantId);
    };
}
```

The function validates required metadata and passes meaningful values to the use case. The service does not need to depend on `MessageHeaders` or the binder. If only the payload is needed, declare `Consumer<OrderPlaced>` to simplify the adapter.

Headers arriving from a broker may undergo type conversion depending on the serializer and binder. If a header arrives as a string in one environment but as an integer in another, normalize the type in the adapter and validate the value before calling the service. Avoid casting directly without inspecting the actual data.

## 3. Distinguishing Business Headers from Broker Metadata

Important concepts can exist across multiple layers with different semantics:

- `eventId` is an application-managed event identifier; a Kafka offset or RabbitMQ delivery tag is broker-managed delivery metadata.
- `aggregateId` identifies a business entity; a Kafka record key can be used for partition selection and per-key ordering. Simply placing `aggregateId` in a header does not mean the binder will automatically use it as the partition key.
- `correlationId` links steps of a business workflow; a trace ID belongs to the tracing system. The two values may be linked but are not necessarily identical.
- `eventVersion` describes the event contract version; the broker's protocol version or CloudEvents specification version serves a different purpose.

In Kafka, record keys and partition metadata have distinct roles. In RabbitMQ, routing keys are an AMQP routing construct, while a headers exchange can match header attributes per configuration. In Pulsar, message keys, properties, and schemas have their own rules. Binders may map some application headers to transport properties, but you cannot assume every header is preserved identically across all brokers.

If a header is mandatory for the consumer to process correctly, verify that the binder supports that header, configure mappings/allow-lists if necessary, and write integration tests against a real broker. Avoid relying on a custom header that only works in the Test Binder.

## 4. Why Events Need Versioning Information

Events are often retained longer than the lifetime of a single application release. An older producer may still emit events using an old schema while a new consumer is already deployed; a new consumer may also need to replay historical data. If the payload structure changes without a versioning convention, consumers may decode incorrectly, drop facts, or misinterpret business meaning.

Event versioning helps consumers and schema management systems determine how to read the payload. It is especially critical when:

- Adding, renaming, or removing fields in the payload.
- Changing data types or field interpretation rules.
- Consumers must support multiple producer versions during rolling deployments.
- Replaying historical events after the system has been upgraded.
- Multiple services are deployed independently and cannot be upgraded simultaneously.

Do not bump the version merely for internal Java class refactoring. The version must reflect changes to the data contract or event semantics visible to consumers.

## 5. Where Should Version Information Live?

There are several ways to represent versions. Choose an authoritative source for consumers to determine the schema:

| Representation | Example | When suitable |
|---|---|---|
| Field in event envelope | `eventVersion: 2` | Application contract needs to read version independently of transport |
| Message header | `eventVersion: 2` | Binder and broker preserve headers, consumer needs to route or select a decoder |
| Schema registry | Schema ID/version attached to record | Using schema-based formats with lifecycle-managed registries |
| CloudEvents attribute | `dataschema` or `eventversion` extension | Needing a CloudEvents-compliant event envelope |

If the same version is repeated in the payload, header, and schema registry, define which source is canonical and how mismatches are detected. Otherwise, a producer might emit a version 2 payload while the header still says version 1, causing the consumer to pick the wrong decoder.

A portable option across brokers is placing the contract version in the envelope or tying it to a managed schema ID. You may also mirror the version into a header to aid routing or observability, provided you test the mapping and ensure the two values cannot conflict.

### Contract Version Is Not Class Version

Avoid using Java class names as public contract identifiers, such as `com.example.OrderPlacedV2`, if the class name merely reflects an implementation detail. You can keep the event type stable as `com.example.orders.OrderPlaced` and manage the schema version separately. If a change creates an event with a different business meaning, assign a new event type to clearly express the distinction.

## 6. Evolving Schemas Without Breaking Consumers

When changing an event schema, consider old producers, new producers, old consumers, new consumers, and data already stored in the broker. Common changes:

| Change | Risk | Handling approach |
|---|---|---|
| Adding an optional field with a default value | Old consumers can ignore it; new consumers must handle old data lacking the field | Often compatible if format and schema rules support it |
| Adding a required field without a default | Old consumers or old data may fail to supply a value | Requires a migration plan or publishing a new version |
| Renaming or deleting a field | Old consumers may fail to read; historical data meaning is affected | Maintain the old field during transition or create a new schema/event version |
| Changing a field's data type | May break serializer and consumer compatibility | Evaluate conversion rules; usually requires a new version |
| Changing business meaning of a field | Data still decodes, but consumers may misprocess it | Create a new contract or event type when semantics change |

Common compatibility modes in schema registries:

- **Backward compatibility**: new schema can read data written with the previous schema, according to registry/format rules.
- **Forward compatibility**: previous schema can read data written with the new schema.
- **Full compatibility**: satisfies both directions of compatibility.
- **Transitive compatibility**: checks compatibility across multiple prior versions rather than only the immediately preceding one, depending on the registry.

Identical mode names do not guarantee every schema registry performs identical checks. Read the rules of the specific format and registry in use, especially regarding default fields, nullability, union types, enums, and aliases.

A safe strategy is usually to add fields in a compatible way, deploy consumers capable of reading both old and new data, and only then release producers using the new fields. When breaking changes are unavoidable, create a new schema or event version and execute a clear migration roadmap.

## 7. Consumers Supporting Multiple Versions

If a consumer must accept multiple versions during a transition period, it can route by `eventVersion` and map each version into a stable internal model:

```java
public record OrderPlacedV1(
    String orderId,
    BigDecimal total
) {}

public record OrderPlacedV2(
    String orderId,
    BigDecimal total,
    String currency
) {}

public record OrderCommand(
    String orderId,
    BigDecimal total,
    String currency
) {}
```

An adapter can convert older versions to the internal model:

```java
@Component
public class OrderEventMapper {

    public OrderCommand fromV1(OrderPlacedV1 event) {
        return new OrderCommand(
            event.orderId(),
            event.total(),
            "VND"
        );
    }

    public OrderCommand fromV2(OrderPlacedV2 event) {
        return new OrderCommand(
            event.orderId(),
            event.total(),
            event.currency()
        );
    }
}
```

Using `VND` as the default in this example is only valid if the version 1 contract explicitly specified that currency. Do not infer default values from current environment settings or configuration, as historical data may be misinterpreted.

With JSON payloads, the adapter can inspect the envelope or schema metadata to select the right DTO and map it to `OrderCommand`. With Avro or Protobuf, serializers/deserializers and schema registries can assist reading older schemas; always test how actual versions decode.

Do not let core business services accept multiple versioned DTOs. Isolate compatibility logic at the boundary layer, convert into a unified internal model, and then invoke the use case.

## 8. CloudEvents and Standardized Event Metadata

CloudEvents is an event envelope specification that standardizes attributes such as:

- `specversion`: version of the CloudEvents specification.
- `id`: event identifier.
- `source`: event origin.
- `type`: event type.
- `subject`: subject that the event describes.
- `time`: occurrence timestamp.
- `datacontenttype`: content type of the data section.
- `dataschema`: schema identifier for the data section, if present.

Extension attributes can carry additional context by convention, such as tenant or correlation ID. CloudEvents helps disparate systems share a consistent envelope, though it does not define your business schema or per-event-type compatibility policies.

Distinguish `specversion` from the event schema version. `specversion: 1.0` indicates the CloudEvents specification version; it does not mean the `OrderPlaced` payload is version 1. To manage schema versions, use `dataschema`, a contract-defined extension attribute, or an appropriate schema registry.

The same event can be represented in CloudEvents JSON format:

```json
{
  "specversion": "1.0",
  "id": "evt-1007",
  "source": "/services/order-service",
  "type": "com.example.orders.OrderPlaced",
  "subject": "orders/order-1007",
  "time": "2026-11-24T10:15:30Z",
  "datacontenttype": "application/json",
  "dataschema": "https://schemas.example.com/orders/order-placed/2",
  "data": {
    "orderId": "order-1007",
    "customerId": "customer-42",
    "total": 1250000,
    "currency": "VND"
  }
}
```

In this example, `dataschema` identifies the specific schema; `specversion` remains the CloudEvents version. When using CloudEvents with Spring Cloud Stream, verify which representation your binder and converter support: envelope in payload or mapping attributes to transport headers. Do not assume the binder automatically converts all CloudEvents attributes into broker headers.

## 9. Configuring and Testing Headers in Spring Cloud Stream

A binding can declare its content type and destination:

```yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.placed
          content-type: application/json
```

A function constructs a message with agreed-upon headers:

```java
@Configuration
public class OrderFunctions {

@Bean
Function<PlaceOrder, Message<OrderPlaced>> publishOrder(
        OrderApplicationService service) {

    return command -> {
        OrderPlaced event = service.place(command);

        return MessageBuilder
            .withPayload(event)
            .setHeader("eventType", "com.example.orders.OrderPlaced")
            .setHeader("eventVersion", 2)
            .setHeader("eventId", event.eventId())
            .setHeader("correlationId", command.correlationId())
            .build();
    };
}
}
```

This snippet assumes `OrderPlaced` has an `eventId()` method and the command has `correlationId()`. In a real application, ensure the event ID is generated once for the event and kept unchanged during replays rather than generating a new ID on every producer-level retry.

Header creation can be verified directly with a unit test:

```java
@Test
void publishesOrderWithContractMetadata() {
    OrderApplicationService service = mock(OrderApplicationService.class);
    OrderFunctions functions = new OrderFunctions();

    PlaceOrder command = new PlaceOrder("order-1007", "checkout-9001");
    OrderPlaced event = sampleOrderPlaced();

    when(service.place(command)).thenReturn(event);

    Message<OrderPlaced> message =
        functions.publishOrder(service).apply(command);

    assertThat(message.getHeaders().get("eventType"))
        .isEqualTo("com.example.orders.OrderPlaced");
    assertThat(message.getHeaders().get("eventVersion")).isEqualTo(2);
    assertThat(message.getHeaders().get("correlationId"))
        .isEqualTo("checkout-9001");
}
```

This is an illustrative example; constructors and bean organization in your project may differ. Unit tests verify that the adapter builds metadata according to the contract. The Spring Cloud Stream Test Binder can test messages across in-memory bindings. Integration tests with a real broker are required to verify header mapping, header data types, serializers, partitioning/routing, and message readability.

A test suite should cover:

1. Required header is missing or has the wrong type.
2. Unsupported event type received by the consumer.
3. Both old and new event versions handled according to policy.
4. Incompatible schemas rejected in a controlled manner.
5. Correlation ID and event ID preserved across required steps.
6. Actual binder transmits required headers across the broker.
7. Failed messages handled according to configured retries or DLQ.

## 10. Header and Versioning Management Checklist

- The payload contains core facts describing what happened; headers contain metadata needed for transport, routing, or observability.
- Every custom header has a clearly defined name, type, meaning, origin, and required/optional rule.
- Choose one authoritative source for event type and event schema version.
- Do not confuse the event schema version with the CloudEvents version or broker version.
- Assess compatibility when adding, renaming, or removing fields and when replaying historical data.
- Use a stable event ID for auditing and idempotency; use correlation ID for flow tracing.
- Do not treat tenant or role headers as authorization proof unless the sender is authenticated.
- Do not put secrets or sensitive data into headers.
- Verify header limits and mappings of the actual binder/broker.
- Test payload, headers, schema compatibility, and version migration together.

Business headers and versioning information help services interpret events consistently over time. When payloads, application metadata, transport metadata, and schema versions have clear boundaries, producers can evolve contracts safely while consumers continue processing both old and new data without depending on implementation details of a single broker.

# Deserializer for Multiple Payload Types

A Kafka topic can carry multiple event types, such as `OrderCreatedEvent` and `PaymentCapturedEvent`. The consumer must determine the appropriate Java type for each record before the listener processes it. Spring Kafka supports several strategies: using type headers with `JsonDeserializer`, using `@KafkaHandler` to dispatch by payload type, wrapping events in an envelope with a type discriminator field, or splitting topics/listeners per schema.

In the `SPRING_KAFKA_MESSAGING` module, producers send records with `KafkaTemplate` and consumers receive records with `@KafkaListener`. Serialization is a two-way contract: the producer turns objects into bytes, and the consumer turns bytes back into data types the application understands. When a topic holds multiple payload types, the contract must specify which type each record belongs to and how the consumer handles unknown types.

## 1. Why Does a Consumer Need to Identify Multiple Payload Types?

Suppose the `domain-events` topic receives events from multiple business domains:

```text
domain-events
├── OrderCreatedEvent
├── PaymentCapturedEvent
├── OrderCancelledEvent
└── ShipmentDispatchedEvent
```

All records are stored as bytes in Kafka. The broker does not store Java objects and cannot tell on its own whether a JSON document is an `OrderCreatedEvent` or a `PaymentCapturedEvent`. The consumer must rely on metadata or payload structure to choose the deserialization target type.

If a consumer always deserializes every record into a single fixed class, records of other types may fail, lose fields, or become domain-incorrect objects. Before selecting a deserializer strategy, clarify:

- Does a single topic truly need to carry multiple event types, or can they be split into separate topics?
- Does the producer emit metadata identifying the event type?
- Do producer and consumer share Java classes, or only language-agnostic schemas?
- What should the consumer do when encountering an unknown event type or schema version?

## 2. Strategies for Multi-Type Deserialization

| Strategy | How type is identified | Best suited when |
|---|---|---|
| JSON type headers | Header written into records by `JsonSerializer` | Producer and consumer both use Spring Kafka JSON serializer and deserializer |
| Type mapping | Stable token in type header mapped to each service's class | Producer and consumer have different packages/classes |
| Event envelope | `eventType` field inside JSON payload | You want contracts independent of Java class names and polyglot support |
| One topic per payload type | Topic determines schema; listener/factory has a fixed type | Events have different lifecycles, access controls, or retention |
| Custom deserializer/converter | Application logic or schema registry determines type | Special schema or format requirements exist |

No single strategy fits every system. If each topic has only one payload type, using a strongly typed listener is usually simplest. When multiple events intentionally share a topic, type headers or envelopes help consumers route clearly.

## 3. Using JSON Type Headers with `JsonDeserializer`

Spring Kafka's `JsonSerializer` can add type information to Kafka headers. `JsonDeserializer` reads that type information to instantiate the matching payload class. This is convenient when producer and consumer both use Spring Kafka and agree on type header conventions.

Example with two event types:

Each record is placed in its own Java file in the project:

```java
import java.math.BigDecimal;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        BigDecimal total
) {}

public record PaymentCapturedEvent(
        String eventId,
        String paymentId,
        String orderId,
        BigDecimal amount
) {}
```

The producer can send both object types through a single `KafkaTemplate<String, Object>` if the serializer is configured to serialize those types:

This example assumes the application has declared a `ProducerFactory<String, Object>` and `KafkaTemplate<String, Object>` using `StringSerializer` for keys and `JsonSerializer` for values. Using `Object` allows sending multiple classes at the cost of compile-time type checking; use it only in intentional adapter boundaries.

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class DomainEventPublisher {

    private final KafkaTemplate<String, Object> kafkaTemplate;

    public DomainEventPublisher(KafkaTemplate<String, Object> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publishOrderCreated(OrderCreatedEvent event) {
        kafkaTemplate.send("domain-events", event.orderId(), event);
    }

    public void publishPaymentCaptured(PaymentCapturedEvent event) {
        kafkaTemplate.send("domain-events", event.orderId(), event);
    }
}
```

With Spring Kafka's default JSON serializer, type headers are attached to records. The consumer uses `JsonDeserializer` to read the type header and instantiate the matching class. Example configuration:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      group-id: domain-event-router
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.use.type.headers: true
        spring.json.trusted.packages: com.acme.events
```

`spring.json.use.type.headers: true` instructs the deserializer to use type headers to identify the class. This is common default behavior for `JsonDeserializer`, though declaring it explicitly makes intent clear. `trusted.packages` restricts the packages the deserializer may instantiate; trust only the required event packages.

Type headers carry type metadata supplied by the producer. If the consumer lacks the matching class, the package is untrusted, or a token cannot be mapped, deserialization may fail before the listener is invoked. Manage classpaths and mappings across services carefully.

## 4. Using Type Mapping to Avoid Coupling to Producer Java Packages

By default, JSON type headers may contain full class names. This creates coupling between producer and consumer: renaming a package or class can prevent older consumers from resolving the type.

Spring Kafka supports `spring.json.type.mapping` to map a short token to a concrete class. Producer and consumer share the same token while mapping it to classes in each service's own package.

Producer example:

```yaml
spring:
  kafka:
    producer:
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        spring.json.type.mapping: "orderCreated:com.acme.orders.contract.OrderCreatedEvent,paymentCaptured:com.acme.payments.contract.PaymentCapturedEvent"
```

The consumer can map those tokens to its own contract classes:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.use.type.headers: true
        spring.json.trusted.packages: com.acme.billing.contract
        spring.json.type.mapping: "orderCreated:com.acme.billing.contract.OrderCreated,paymentCaptured:com.acme.billing.contract.PaymentCaptured"
```

This example assumes the consumer defines `OrderCreated` and `PaymentCaptured` with structures compatible with the producer payloads. The tokens `orderCreated` and `paymentCaptured` form the shared contract agreed upon by both sides; Java packages do not need to match.

When renaming internal classes, keep tokens stable as long as schemas remain compatible. Never reuse one token for two incompatible schemas. Deploy mappings in sync with running consumer versions; if a producer emits a new token before consumers support it, records may fail deserialization.

## 5. Dispatching Payloads by Type with `@KafkaHandler`

Once `JsonDeserializer` instantiates the right class, you can use a class-level `@KafkaListener` with multiple `@KafkaHandler` methods. Spring Kafka selects the method matching the actual payload type.

```java
import org.springframework.kafka.annotation.KafkaHandler;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
@KafkaListener(
        id = "domainEventListener",
        topics = "domain-events",
        groupId = "domain-event-router"
)
public class DomainEventListener {

    @KafkaHandler
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Order created: " + event.orderId());
    }

    @KafkaHandler
    public void onPaymentCaptured(PaymentCapturedEvent event) {
        System.out.println("Payment captured: " + event.paymentId());
    }

    @KafkaHandler(isDefault = true)
    public void onUnknownEvent(Object payload) {
        String payloadType = payload == null
                ? "null"
                : payload.getClass().getName();
        throw new IllegalArgumentException(
                "Unsupported event payload: " + payloadType
        );
    }
}
```

Each `@KafkaHandler` method handles one payload type. The `isDefault = true` method acts as a fallback branch when no specific handler matches. In this example, the fallback throws an exception so the error handler can retry or route the record to a dead-letter topic per policy.

Do not merely log an unsupported event and return normally if the system must guarantee new event types are not silently dropped. A listener returning normally is typically treated as successful processing and its offset may be committed. Decide explicitly whether unknown events are errors requiring recovery, ignorable events, or records to persist for later processing.

`@KafkaHandler` dispatches based on the already-deserialized Java type. It does not inspect a JSON `eventType` field to choose a class. If the deserializer always produces a `Map` or `JsonNode`, handlers accepting `OrderCreatedEvent` will not be selected automatically.

## 6. Using an Event Envelope for Java-Class-Independent Contracts

Another option is wrapping every event type in a shared structure. The envelope carries the event type, schema version, and payload:

```json
{
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "payload": {
    "eventId": "evt-1001",
    "orderId": "order-1001",
    "total": 1250000
  }
}
```

Java model:

```java
import com.fasterxml.jackson.databind.JsonNode;

public record EventEnvelope(
        String eventType,
        int schemaVersion,
        JsonNode payload
) {}
```

The handlers used by the listener can follow a contract such as:

```java
public interface OrderEventHandler {
    void handle(OrderCreatedEvent event);
}

public interface PaymentEventHandler {
    void handle(PaymentCapturedEvent event);
}
```

The consumer deserializes every record into `EventEnvelope` and routes by `eventType`:

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class EnvelopeEventListener {

    private final ObjectMapper objectMapper;
    private final OrderEventHandler orderHandler;
    private final PaymentEventHandler paymentHandler;

    public EnvelopeEventListener(
            ObjectMapper objectMapper,
            OrderEventHandler orderHandler,
            PaymentEventHandler paymentHandler) {
        this.objectMapper = objectMapper;
        this.orderHandler = orderHandler;
        this.paymentHandler = paymentHandler;
    }

    @KafkaListener(topics = "domain-events", groupId = "envelope-router")
    public void listen(EventEnvelope envelope) throws JsonProcessingException {
        if (envelope == null || envelope.eventType() == null
                || envelope.payload() == null) {
            throw new IllegalArgumentException("Event envelope is incomplete");
        }
        if (envelope.schemaVersion() != 1) {
            throw new IllegalArgumentException(
                    "Unsupported schema version: " + envelope.schemaVersion());
        }

        switch (envelope.eventType()) {
            case "OrderCreated" -> orderHandler.handle(
                    objectMapper.treeToValue(
                            envelope.payload(), OrderCreatedEvent.class));
            case "PaymentCaptured" -> paymentHandler.handle(
                    objectMapper.treeToValue(
                            envelope.payload(), PaymentCapturedEvent.class));
            default -> throw new IllegalArgumentException(
                    "Unsupported event type: " + envelope.eventType());
        }
    }
}
```

With this approach, `JsonDeserializer` only needs to construct `EventEnvelope`; the inner payload is converted to a concrete type after reading `eventType`. Consumer configuration can set a default type and ignore type headers:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.acme.messaging.EventEnvelope
        spring.json.use.type.headers: false
        spring.json.trusted.packages: com.acme.messaging
```

Envelopes offer an explicit contract, work well across languages, and require no knowledge of producer class names on the consumer. In return, the application must manage the registry of event types, schema versions, and payload conversion logic. Check `schemaVersion` and reject or route unsupported versions to recovery; never assume all payloads with the same `eventType` share the exact same structure.

## 7. When Each Topic Has Only One Payload Type

If events have different lifecycles, access controls, retention, or schema evolution rates, splitting topics is often simpler than multiplexing multiple payload types onto one topic.

Example where each topic has a typed listener:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    private final OrderEventHandler orderHandler;

    public OrderCreatedListener(OrderEventHandler orderHandler) {
        this.orderHandler = orderHandler;
    }

    @KafkaListener(
            topics = "orders.created",
            groupId = "order-projection",
            containerFactory = "orderEventListenerContainerFactory"
    )
    public void onOrderCreated(OrderCreatedEvent event) {
        orderHandler.handle(event);
    }
}

@Component
class PaymentCapturedListener {

    private final PaymentEventHandler paymentHandler;

    public PaymentCapturedListener(PaymentEventHandler paymentHandler) {
        this.paymentHandler = paymentHandler;
    }

    @KafkaListener(
            topics = "payments.captured",
            groupId = "payment-projection",
            containerFactory = "paymentEventListenerContainerFactory"
    )
    public void onPaymentCaptured(PaymentCapturedEvent event) {
        paymentHandler.handle(event);
    }
}
```

Each container factory can use a `JsonDeserializer` with its own target type. The consumer then needs no polymorphic deserialization or type-header dispatching. This layout is easy to monitor and enables per-topic retry/DLT, concurrency, ACL, and retention settings.

Do not split topics merely because two events have different classes if they genuinely belong to the same logical stream and require shared partition ordering. Base the decision on contracts, ownership, consumption patterns, and operations.

## 8. Handling Invalid Payloads or Unknown Types

Deserialization occurs before the listener method is invoked. Therefore, malformed JSON, unresolvable type headers, or untrusted packages will bypass a `try/catch` inside the listener. Error handling must be configured at the container level.

Spring Kafka provides `ErrorHandlingDeserializer` to wrap the actual deserializer. Example:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.use.type.headers: true
        spring.json.trusted.packages: com.acme.billing.contract
        spring.json.type.mapping: "orderCreated:com.acme.billing.contract.OrderCreated,paymentCaptured:com.acme.billing.contract.PaymentCaptured"
```

`ErrorHandlingDeserializer` catches failures from the delegate and attaches error details according to Spring Kafka's mechanism so an error handler/recoverer can process them. Configure `DefaultErrorHandler` and dead-letter publishing appropriately to retain failed records. Test deserialization failure paths explicitly because the listener method will not receive a normal payload.

For valid event types not yet supported by the application, the `@KafkaHandler` default branch or envelope `switch` must explicitly decide between retry, DLT, or intentional skip. Never infinitely retry a type the consumer cannot understand; that is usually a contract issue requiring alerting and recovery.

## 9. Safety in Multi-Type Deserialization

Type headers influence which class is instantiated from untrusted bytes. Never widen the range of instantiable types beyond what is necessary.

- Configure `trusted.packages` only for packages containing required event contracts.
- Avoid `*` or overly broad trusted packages in production.
- Use stable type mapping tokens rather than letting producers dictate arbitrary Java class names on consumers.
- Do not enable broad Jackson default typing for untrusted Kafka payloads.
- Validate data after deserialization; an object that deserializes cleanly is not guaranteed to be valid business data.
- Do not put secrets or unnecessary personal data into type headers or custom headers.
- Define clear policies for unknown event types, new schema versions, and malformed payloads.

Type mapping reduces package coupling, but it does not replace schema governance or payload validation. Consumers must still restrict mappable classes and validate inputs.

## 10. Schema Evolution on Multi-Event Topics

When multiple event types share a topic, consumers must stay compatible with producer versions deployed concurrently. Key principles:

- Use stable event names such as `OrderCreated` rather than internal class names as the sole contract.
- Define schemas and field semantics; avoid changing a field's meaning while keeping its name.
- Prefer compatible changes, such as adding optional fields with sensible defaults.
- Do not remove or change field types while older consumers may still read new records.
- Use `schemaVersion` when envelopes or schema registries require explicit version management.
- Run compatibility tests between supported producer and consumer versions.
- Define support windows for older event types and a deprecation process before retiring them.

When using Schema Registry with Avro, Protobuf, or JSON Schema, the registry manages schemas/versions alongside the corresponding serializers/deserializers. Spring Kafka JSON type mapping is a class/token mapping mechanism; it does not replace a schema registry's compatibility checks.

## 11. Testing Multi-Type Deserializers

Test at both the configuration level and through live Kafka flows:

- **Type header test:** send each event using `JsonSerializer` and verify `JsonDeserializer` constructs the matching class.
- **Type mapping test:** producer and consumer use different packages/classes with the same tokens; verify the consumer resolves its local classes.
- **Handler dispatch test:** verify `@KafkaHandler` routes to the right method for each payload type.
- **Envelope test:** verify `eventType` and `schemaVersion` select the right handler and convert payloads into the expected classes.
- **Unknown type test:** send an unsupported token or event type and verify the default branch/error handler/DLT behaves per policy.
- **Malformed JSON test:** send invalid payloads and verify `ErrorHandlingDeserializer` and the error handler process them.
- **Compatibility test:** verify older consumers can read payloads emitted by newer producer versions.
- **Security test:** verify classes outside trusted packages are rejected.

Embedded Kafka or Testcontainers are well suited for integration testing. Use dedicated topics and consumer groups per test so stale offsets do not skew results.

## 12. Choosing a Strategy by Scenario

| Scenario | Recommended option |
|---|---|
| One topic holding multiple Java POJOs, both producer and consumer use Spring Kafka | JSON type headers + `JsonDeserializer` |
| Two services use different Java packages while sharing event schemas | Type mapping with stable tokens |
| Polyglot producers or no desire to rely on Java class names | Event envelope with `eventType` and `schemaVersion` |
| Each event type has distinct retention, ACLs, or retry policies | Separate topics and listener factories per type |
| Using Avro/Protobuf/JSON Schema with compatibility enforcement | Corresponding serializers/deserializers and Schema Registry |
| Need specialized control over byte-to-object conversion | Custom deserializer or message converter |

Do not choose `KafkaTemplate<String, Object>` just to shorten code if a producer only emits one event type. Concrete types allow compiler checks on payloads and make contracts clearer. Use a multi-type template only when it is an intentional multi-event stream and the serializer supports all published event types.

## 13. Common Mistakes

- **Disabling type headers while expecting `JsonDeserializer` to distinguish multiple classes:** without type metadata, the consumer needs a default type or an envelope/custom resolver.
- **Using `Object` and assuming payloads are always concrete POJOs:** without type headers or a target type, JSON objects may deserialize into `Map`.
- **Producer and consumer disagreeing on type mapping tokens:** tokens fail to resolve or map to the wrong schema.
- **Overly broad trusted packages:** increases exposure to deserializing unintended classes.
- **`@KafkaHandler` not invoked:** actual payload lacks a matching type because the deserializer produced `Map`, `JsonNode`, or another class.
- **Unknown events silently ignored:** normal listener returns can commit offsets even though the event was never processed.
- **Catching errors inside the listener when failures happen before the listener:** deserialization failures require container-level error handlers/recoverers.
- **Treating type mapping as a schema registry:** token-to-class mapping does not check schema compatibility.
- **Over-splitting topics or dumping everything into one topic:** both carry costs; decide based on contracts and operations.
- **Failing to test older consumers:** newer producers may emit types or schemas that running consumers do not yet support.

## 14. Pre-Deployment Checklist for Multi-Type Deserialization

- [ ] Clearly selected type headers, type mapping, envelope, or separate topics.
- [ ] Producer serializer and consumer deserializer agree on wire format.
- [ ] Type tokens/event types form stable contracts independent of internal class names.
- [ ] `trusted.packages` contains only required packages.
- [ ] `@KafkaHandler` defines handlers per type plus an unknown-type policy.
- [ ] Envelopes validate `eventType`, `schemaVersion`, and payload.
- [ ] Deserialization failures are handled at the container via error handler/recoverer.
- [ ] Retry/DLT policies do not loop infinitely on unsupported event types.
- [ ] Schema evolution is compatible with concurrently deployed producers and consumers.
- [ ] Integration tests cover valid payloads, unknown types, malformed JSON, and new schema versions.

Deserializers for multiple payload types require an explicit event-identification contract. Type headers and mappings fit Spring Kafka JSON systems; envelopes fit when decoupling from Java classes; separate topics fit when event types differ operationally. Combining the chosen strategy with trusted-package controls, schema compatibility, and error handling enables consumers to process multiple event types safely and at scale.

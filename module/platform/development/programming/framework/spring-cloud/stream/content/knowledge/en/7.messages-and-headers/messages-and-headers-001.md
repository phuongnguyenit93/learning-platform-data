# `Message<T>` Structure: Payload, Headers, and Immutability

In Spring Cloud Stream, an event can be passed through a function as a plain payload or as a `Message<T>`. `Message<T>` is a Spring Messaging contract consisting of two parts: the **payload** containing business data and **headers** containing metadata describing the message. When using `Message<T>`, a function can read information such as correlation IDs, origin sources, event types, or creation timestamps, while also deciding which metadata to preserve when creating the next message.

Understanding message immutability properly is crucial when processing event streams. Spring provides APIs to create new messages and build new headers instead of modifying a received message directly. However, structural immutability of the message does not automatically make the payload object or objects stored in headers immutable.

## 1. Structure of Message<T>

`org.springframework.messaging.Message<T>` is the interface representing a message. It provides two main components:

| Component | API | Role |
| --- | --- | --- |
| Payload | `getPayload()` | The primary data that the application wants to exchange, such as an `OrderCreated` or a JSON string. |
| Headers | `getHeaders()` | A collection of key/value pairs describing the message, such as `correlationId`, `contentType`, or source information. |

Type `T` is the payload type. For example, `Message<OrderCreated>` means the payload has type `OrderCreated`, while headers remain the Spring Messaging metadata collection.

```java
import org.springframework.messaging.Message;

void handle(Message<String> message) {
    String body = message.getPayload();
    Object correlationId = message.getHeaders().get("correlationId");

    System.out.println("Payload: " + body);
    System.out.println("Correlation: " + correlationId);
}
```

If a function only needs to process business data and does not need to read or create metadata, it can declare its parameter as `OrderCreated` or `String`. Spring Cloud Stream passes the payload into the function. When header access is needed, declare the parameter or return value as `Message<T>`.

## 2. Payload Holds Business Data

The payload is the main body of the message. For an order processing service, the payload might be a record:

```java
import java.math.BigDecimal;

public record OrderCreated(
        String orderId,
        String customerId,
        BigDecimal total
) {}
```

A message can hold an `OrderCreated` payload along with headers describing the transport context:

```java
Message<OrderCreated> message = MessageBuilder
        .withPayload(new OrderCreated(
                "ORD-1001",
                "CUS-42",
                new BigDecimal("125000.00")
        ))
        .setHeader("correlationId", "corr-7f2a")
        .setHeader("source", "checkout-service")
        .build();
```

In this example, `orderId`, `customerId`, and `total` are business data, so they belong in the payload. `correlationId` helps link operations belonging to the same processing flow; `source` describes where the event originated, so it belongs in the headers.

Do not move all information into headers. Data that needs to be persisted, schema-validated, reused by consumers, or carries business meaning should reside in the payload. Headers are suited for metadata used for routing, tracing, correlation, formatting, and message handling.

## 3. Headers as Key-Value Metadata

Headers provide context alongside the payload without changing the business data structure. Some common headers include:

| Header | Purpose |
| --- | --- |
| `id` | Message identifier managed by Spring Messaging; new messages typically receive a new ID. |
| `timestamp` | Message creation timestamp according to Spring Messaging's mechanism, if present. |
| `contentType` | Hints at the content format, such as `application/json`; Spring Cloud Stream also has content type configuration at the binding level. |
| `correlationId` | Links the message to a related request, workflow, or event chain. |
| `traceparent` | Carries trace context following the W3C Trace Context standard when tracing is integrated. |
| `source` or `eventType` | Application-defined metadata describing the origin or event type. |

`id` and `timestamp` are standard Spring Messaging headers. Headers such as `correlationId`, `source`, or `eventType` are typically application conventions; participating services in the flow must agree on their names, data types, and meanings.

Headers can be used to support routing or observability, but they should not become the sole place storing information required to understand the event. Consumers should read the payload according to an agreed-upon schema and rely on headers only when the event contract explicitly specifies it.

## 4. Creating Messages with MessageBuilder

Do not implement `Message<T>` manually or build a custom header map to replace Spring's API. `MessageBuilder` is the standard way to create a new message.

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> message = MessageBuilder
        .withPayload("ORDER_CREATED")
        .setHeader("eventType", "OrderCreated")
        .setHeader("correlationId", "corr-7f2a")
        .build();
```

Key builder operations:

| API | Usage |
| --- | --- |
| `withPayload(payload)` | Starts building a message with a new payload. |
| `setHeader(name, value)` | Sets or replaces the value of a header. |
| `setHeaderIfAbsent(name, value)` | Sets the header only if it is not already present. |
| `copyHeaders(map)` | Copies headers from a map into the builder. |
| `copyHeadersIfAbsent(map)` | Copies only headers that have not yet been set. |
| `removeHeader(name)` | Removes a header from the message being built. |
| `build()` | Creates a new `Message<T>` instance. |

For example, creating a message with default headers if not supplied by upstream:

```java
Message<String> message = MessageBuilder
        .withPayload("ORDER_CREATED")
        .setHeaderIfAbsent("source", "order-service")
        .setHeaderIfAbsent("eventType", "OrderCreated")
        .build();
```

`setHeaderIfAbsent` is useful when an intermediate component adds default metadata while preserving values provided by an earlier component.

## 5. Immutability of Message and MessageHeaders

`Message<T>` is designed as an already-constructed message object, and `MessageHeaders` exposes a header collection that does not allow direct modification via the map API. Therefore, the following operation is not a valid way to update a header:

```java
message.getHeaders().put("source", "new-service"); // Direct modification is not supported
```

The header map of `MessageHeaders` is immutable; direct modification attempts typically result in `UnsupportedOperationException`. To change metadata, create a new message using the builder:

```java
Message<String> updated = MessageBuilder
        .fromMessage(message)
        .setHeader("source", "new-service")
        .build();
```

`fromMessage(message)` initializes a builder from an existing message. After modifying headers and calling `build()`, the application gets a new message; the original message retains its old headers.

Immutability here refers to the structural immutability of the message and header collection. It does not mean deep immutability:

- If the payload is a mutable object, code can still modify its internal state after the message is created.
- If a header contains a mutable object, that object can still be modified through another reference.
- Creating a new message does not automatically deep-copy the payload or every header value.

Therefore, prefer immutable payloads such as Java records or value objects without setters. For metadata, prefer strings, numbers, enums, or stable value types. If mutable objects must be used, manage ownership carefully and avoid sharing references that could be modified concurrently.

## 6. Transforming Payload and Preserving Needed Headers

When a function receives a message and produces a payload of a different type, create a new message and explicitly choose which headers to forward. Do not assume that every internal Spring or binder header should be emitted to the downstream destination.

For example, transforming `OrderCreated` into `OrderAccepted` and preserving `correlationId`:

```java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public record OrderAccepted(String orderId, String status) {}

@Bean
public Function<Message<OrderCreated>, Message<OrderAccepted>> acceptOrder() {
    return input -> {
        OrderCreated order = input.getPayload();
        Object correlationId = input.getHeaders().get("correlationId");

        OrderAccepted result = new OrderAccepted(
                order.orderId(),
                "ACCEPTED"
        );

        return MessageBuilder.withPayload(result)
                .setHeader("correlationId", correlationId)
                .setHeader("eventType", "OrderAccepted")
                .setHeader("source", "order-service")
                .build();
    };
}
```

The function reads the payload using `getPayload()`, retrieves the metadata to keep from `getHeaders()`, and creates a new message. This approach makes the output message contract explicit: only `correlationId`, `eventType`, and `source` are intentionally placed onto the new message.

If you want to keep many headers from the old message, you can use `copyHeaders(input.getHeaders())`, then override or remove unsuitable headers. Think carefully before copying all headers, as some headers only have meaning in an internal context or contain types that cannot be serialized to the broker.

## 7. Reading, Adding, Replacing, and Removing Headers

Reading a header:

```java
Object value = message.getHeaders().get("correlationId");
String correlationId = value instanceof String text ? text : null;
```

Setting or replacing a header with the builder:

```java
Message<String> updated = MessageBuilder.fromMessage(message)
        .setHeader("source", "billing-service")
        .build();
```

Adding only if not already present:

```java
Message<String> updated = MessageBuilder.fromMessage(message)
        .setHeaderIfAbsent("source", "billing-service")
        .build();
```

Removing a header:

```java
Message<String> sanitized = MessageBuilder.fromMessage(message)
        .removeHeader("temporaryDebugInfo")
        .build();
```

All the examples above create a new message. Avoid calling `put`, `remove`, or other mutating operations directly on `message.getHeaders()`.

## 8. Using Message<T> in Supplier, Function, and Consumer

Spring Cloud Stream allows functions to work directly with `Message<T>` when control over both payload and headers is needed.

### Supplier Emitting Messages with Metadata

```java
import java.util.UUID;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Bean
public Supplier<Message<String>> orderEvents() {
    return () -> MessageBuilder.withPayload("ORDER_CREATED")
            .setHeader("eventType", "OrderCreated")
            .setHeader("correlationId", UUID.randomUUID().toString())
            .build();
}
```

Each time the supplier creates a message, the payload and metadata are packaged together. In real applications, the payload is typically a DTO or record rather than an illustrative string.

### Function Reading and Creating a New Message

```java
@Bean
public Function<Message<OrderCreated>, Message<OrderAccepted>> acceptOrder() {
    return input -> {
        OrderCreated order = input.getPayload();
        return MessageBuilder.withPayload(
                    new OrderAccepted(order.orderId(), "ACCEPTED"))
                .setHeader("correlationId",
                        input.getHeaders().get("correlationId"))
                .build();
    };
}
```

### Consumer Reading Payload and Headers

```java
import java.util.function.Consumer;

@Bean
public Consumer<Message<OrderCreated>> auditOrder() {
    return message -> {
        OrderCreated order = message.getPayload();
        Object correlationId = message.getHeaders().get("correlationId");

        System.out.printf("Order %s, correlation %s%n",
                order.orderId(), correlationId);
    };
}
```

If a consumer does not need metadata, it can accept `OrderCreated` directly. Use `Message<T>` when headers are genuinely required for processing.

## 9. Headers Crossing Brokers

Headers in `Message<T>` are metadata at the Spring Messaging layer. When a message is sent through Kafka, RabbitMQ, or Pulsar, the binder must map headers to metadata supported by the broker. How headers are mapped, which data types are supported, and which headers pass through can differ across binders and versions.

Points to keep in mind:

- Headers with string or scalar values are generally easier to map and more compatible than custom Java objects.
- Headers containing non-serializable objects may be dropped, cause send failures, or be unreadable at the consumer, depending on the binder.
- Some headers are internal to Spring Integration, Spring Messaging, or the binder; they are not necessarily business metadata to be sent across the broker.
- Brokers have their own limits on header or metadata size. Avoid putting large payloads into headers.
- Headers such as `contentType`, partition keys, or correlation metadata may receive special handling from the binder; follow the binder's conventions.

Do not assume that every header in an input message will automatically appear intact in the output message or at a consumer in another service. If an event contract requires specific metadata, test header mapping through the actual broker and binder configuration.

## 10. Payload Schema and Content Type

Payload and headers work together so consumers can interpret the data. The payload defines the content, while the content type describes the format so the framework or consumer can convert it properly. For example, JSON can be declared via binding configuration:

```yaml
spring:
  cloud:
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.created
          content-type: application/json
        acceptOrder-out-0:
          destination: orders.accepted
          content-type: application/json
```

With `Message<T>`, the `contentType` header can participate in message conversion. However, manage content types through binding configuration or framework conventions rather than manually setting a value that conflicts with the configuration. The payload schema still needs to be designed with versioning and compatibility rules when producers and consumers are deployed independently.

Do not use an `eventType` header as a substitute for a payload schema. `eventType` can help classify events, but consumers still need to understand the payload structure and how to handle schema evolution.

## 11. Safe Header Design Guidelines

A clear set of header conventions helps services collaborate more effectively:

1. **Consistent naming:** use clear names and consistent casing, such as `correlationId`, `eventType`, and `source`.
2. **Define data types:** standardize on `String`, numbers, or scalar types per header; avoid letting producers send arbitrary types.
3. **Separate metadata from business data:** information that needs to be stored or validated against a schema belongs in the payload.
4. **Keep only needed metadata:** when transforming a message, copy only headers meaningful to downstream processing.
5. **Avoid sensitive information:** do not place access tokens, passwords, or unnecessary personal data in headers, as metadata may appear in logs and observability tools.
6. **Do not rely on header ordering:** headers are a key/value collection; applications should not depend on iteration order.
7. **Limit size:** metadata should stay small to avoid exceeding broker limits and increasing transport overhead.
8. **Test broker propagation:** verify that headers are actually preserved with the data types required by the contract.

In particular, never use a header that a producer can arbitrarily alter as the sole basis for authorization or authentication decisions. Security decisions must rely on trusted identity sources and appropriate authentication mechanisms.

## 12. Testing Immutability and Headers

Tests should verify payload, headers, and new message creation behavior. For example, with JUnit:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class MessageHeaderTest {

    @Test
    void createsNewMessageWhenHeaderChanges() {
        Message<String> original = MessageBuilder.withPayload("ORDER_CREATED")
                .setHeader("source", "checkout")
                .build();

        Message<String> updated = MessageBuilder.fromMessage(original)
                .setHeader("source", "order-service")
                .build();

        assertEquals("checkout", original.getHeaders().get("source"));
        assertEquals("order-service", updated.getHeaders().get("source"));
        assertEquals("ORDER_CREATED", updated.getPayload());
        assertNotEquals(original, updated);
    }
}
```

This test verifies that the original message retains its old header while the new message has the updated header. Additional tests can cover missing headers, `setHeaderIfAbsent`, header removal, and forwarding `correlationId`.

The test binder helps verify message flows within the application without a real broker. To confirm that headers are mapped correctly across Kafka, RabbitMQ, or Pulsar, integration tests with the corresponding binder and broker are required. Differences in header mapping, serialization, and metadata limits can only be fully verified at the integration layer.

## Conclusion

`Message<T>` combines a payload containing business data with headers containing metadata. `MessageHeaders` does not allow direct map mutation; `MessageBuilder` creates a new message to set, copy, or remove headers. This immutability applies to the message structure and does not automatically protect the internal state of mutable payloads or header objects. When using Spring Cloud Stream, choose meaningful headers, control metadata forwarding, and test binder mapping so messages uphold the contract between services.

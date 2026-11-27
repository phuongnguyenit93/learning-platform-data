# Keeping, Adding, and Removing Headers When Transforming Messages

In Spring Cloud Stream, data is passed between functions as messages. A message has a payload containing business data and headers containing metadata such as correlation ID, event type, schema version, or tracing information. When a `Function` transforms a payload, the application must decide which metadata continues with the message, which metadata needs to be updated, and which metadata must be removed.

This decision directly affects traceability, schema compatibility, security, and routing. Blindly keeping all headers can leak internal data or forward information that only had meaning in an upstream hop. Removing all headers can lose the correlation ID, trace context, or metadata required by downstream consumers. This lesson explains how to manage headers intentionally when transforming messages with `Supplier`, `Function`, and `Consumer`.

## 1. Payloads and Headers Serve Different Roles

The payload is the primary content that the consumer needs to process. For an order event, the payload might contain the order ID, customer, and total amount. Headers add information describing the message or its transport:

| Component | Example | Purpose |
|---|---|---|
| Payload | orderId, customerId, total | Business data |
| Correlation header | correlationId | Links steps within the same processing flow |
| Trace header | traceparent, tracestate | Tracks requests across multiple services |
| Event header | eventType | Describes the event kind |
| Schema header | schemaVersion | Indicates the data contract version |
| Routing header | tenantId, region | Assists routing if the architecture permits |
| Internal header | internal-debug, source-node | Information used only in one hop or environment |

Spring represents messages via the `Message<T>` interface. The payload has type `T`; headers are accessed via `MessageHeaders`:

~~~java
import org.springframework.messaging.Message;

void inspect(Message<OrderCreated> message) {
    OrderCreated order = message.getPayload();
    String correlationId =
            (String) message.getHeaders().get("correlationId");

    System.out.println(order.orderId());
    System.out.println(correlationId);
}
~~~

`MessageHeaders` is an immutable structure. Never mutate the map returned by `getHeaders()` directly. To create a new message, use `MessageBuilder`; the builder constructs a new header set based on the values you copy, add, or remove.

## 2. Keeping Headers When Only Adding Metadata

If the payload does not change and you need to add a header, you can build a new message from the existing message:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderCreated> addSourceHeader(Message<OrderCreated> message) {
    return MessageBuilder.fromMessage(message)
            .setHeader("source-service", "order-api")
            .setHeaderIfAbsent("eventType", "OrderCreated")
            .build();
}
~~~

`MessageBuilder.fromMessage(message)` initializes a builder from the existing message, keeping its current headers. `setHeader` adds a new header or replaces an old value; `setHeaderIfAbsent` sets the value only when the header does not yet exist. After calling `build()`, the result is a new message; the input message and its headers remain untouched.

Choosing between `setHeader` and `setHeaderIfAbsent` depends on metadata ownership. If the current function is responsible for determining `eventType`, use `setHeader` to ensure the value reflects the output event. If you want to preserve information supplied by the producer when present, `setHeaderIfAbsent` is more appropriate.

Do not arbitrarily overwrite `correlationId` or trace context. These values are usually created at the start of the flow and must remain consistent across steps so logs and observability systems can link processing attempts together.

## 3. Transforming the Payload and Keeping Needed Headers

When a `Function` changes the payload type, build the output message with the new payload and then copy headers from the input message. For example, an order validation function receiving `OrderCreated` and emitting `OrderValidated`:

~~~java
import java.time.Instant;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

record OrderCreated(String orderId, String customerId) {}

record OrderValidated(
        String orderId,
        String customerId,
        String status,
        Instant validatedAt) {}

@Configuration
class OrderFunctions {

    @Bean
    Function<Message<OrderCreated>, Message<OrderValidated>> validateOrder() {
        return message -> {
            OrderCreated input = message.getPayload();
            OrderValidated output = new OrderValidated(
                    input.orderId(),
                    input.customerId(),
                    "VALIDATED",
                    Instant.now());

            return MessageBuilder.withPayload(output)
                    .copyHeaders(message.getHeaders())
                    .setHeader("eventType", "OrderValidated")
                    .setHeader("schemaVersion", 2)
                    .removeHeader("internal-debug")
                    .build();
        };
    }
}
~~~

In this example:

- `withPayload(output)` creates a message with the new payload.
- `copyHeaders(message.getHeaders())` copies input headers to the output message.
- `setHeader` updates `eventType` and `schemaVersion` to match the new payload.
- `removeHeader` strips internal headers no longer needed in the next hop.

This approach keeps all headers and then removes known unwanted ones. It fits well when input messages are controlled and the valid header set is well-defined. For flows receiving data from multiple producers or external brokers, consider an allowlist: copy only headers permitted to propagate further.

## 4. Keeping Only Allowed Headers

A message can carry headers added by producers, frameworks, binders, or brokers. Not every header is meaningful in downstream hops. When transforming the payload and crossing another service boundary, an allowlist helps control output metadata:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
class AllowlistFunctions {

    @Bean
    Function<Message<OrderCreated>, Message<OrderValidated>> validateWithAllowlist() {
        return message -> {
            OrderCreated input = message.getPayload();
            OrderValidated output = new OrderValidated(
                    input.orderId(),
                    input.customerId(),
                    "VALIDATED",
                    java.time.Instant.now());

            Object correlationId = message.getHeaders().get("correlationId");
            Object traceparent = message.getHeaders().get("traceparent");

            var builder = MessageBuilder.withPayload(output)
                    .setHeader("eventType", "OrderValidated")
                    .setHeader("schemaVersion", 2);

            if (correlationId != null) {
                builder.setHeader("correlationId", correlationId);
            }
            if (traceparent != null) {
                builder.setHeader("traceparent", traceparent);
            }

            return builder.build();
        };
    }
}
~~~

Here, the output message carries only `correlationId`, `traceparent`, and newly created metadata. Other headers are not copied. If the application uses W3C tracing, ensure the active tracing mechanism handles trace context propagation; the example above simply illustrates retaining a header when present.

An allowlist is useful when:

- Messages arrive from external producers or partially trusted sources.
- A hop needs to strip internal headers, debug details, or sensitive data.
- The payload is published to a different broker where original headers do not share the same semantics.
- The message contract explicitly defines which metadata may cross service boundaries.

Do not copy authentication headers, cookies, tokens, personal information, or infrastructure details to another destination unless the consumer has a clear need and authorization to use them. Unnecessary metadata increases data exposure risk and can push messages over broker header size limits.

## 5. Removing Headers That Are No Longer Relevant

When a header only has meaning within a single processing step, remove it before emitting the message to the next step:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderCreated> removeInternalHeaders(Message<OrderCreated> message) {
    return MessageBuilder.fromMessage(message)
            .removeHeader("internal-debug")
            .removeHeader("temporary-route")
            .removeHeader("legacy-source")
            .build();
}
~~~

`removeHeader(name)` deletes the named header from the constructed message. It can be called multiple times to remove multiple headers. Removing headers does not mutate the input message.

Remove a header when:

- The header only serves debugging or internal processing at a single hop.
- Its value is no longer accurate after the payload was transformed.
- The header contains sensitive data that must not reach downstream consumers.
- Headers from an older broker have no meaning on the new broker.
- The header duplicates or conflicts with standardized output metadata.

Do not delete `correlationId` or trace context merely to make messages smaller if the system relies on them for tracing. Likewise, avoid arbitrarily deleting headers used by the binder or framework for routing, acknowledgement, or conversion. Before removing a specialized header, verify where it originates and where it is consumed.

## 6. Updating Content Type When the Payload Changes

The content type header describes the payload format. If a `Function` changes the payload from a JSON object to a plain text string, the output format metadata should reflect the new content. Example:

~~~java
import org.springframework.http.MediaType;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

Message<String> toText(Message<OrderCreated> input) {
    OrderCreated order = input.getPayload();
    String text = "Order " + order.orderId()
            + " belongs to " + order.customerId();

    return MessageBuilder.withPayload(text)
            .copyHeaders(input.getHeaders())
            .setHeader(MessageHeaders.CONTENT_TYPE, MediaType.TEXT_PLAIN)
            .setHeader("eventType", "OrderSummary")
            .build();
}
~~~

If the payload remains JSON while its schema changes, the content type can stay `application/json`; in that case, update `eventType` or `schemaVersion` per the contract. Do not merely bump a `schemaVersion` header to mask an incompatible change. Producer and consumer must agree on the actual data structure.

Spring selects message converters based on content type and payload type to convert data. If a header declares the wrong format, the consumer may decode inaccurately or hit conversion errors. For JSON data, you can use `MediaType.APPLICATION_JSON`; for plain text content, use `MediaType.TEXT_PLAIN`.

## 7. Standard Headers and Application-Defined Headers

Not all headers are freely managed by the application. Spring Messaging defines several standard headers, such as:

| Header | Meaning | Note |
|---|---|---|
| id | Framework-managed message identifier | Do not manually override |
| timestamp | Message creation timestamp | Do not use in place of business time |
| contentType | Payload content type | Update when payload format changes |
| correlationId | Correlation metadata defined by application or infrastructure conventions | Keep stable across related steps |

`id` and `timestamp` are Spring-managed headers and are effectively read-only. Do not attempt to overwrite them with `setHeader`. If you need a stable event identifier or business occurrence time, create dedicated headers such as `eventId` and `occurredAt`, or include those fields in the payload according to the event contract.

Application-defined headers should have clear names and simple, serializable values—for example, `eventType`, `schemaVersion`, `correlationId`, `tenantId`, or `traceparent`. Avoid colliding with standard header names or binder-specific headers.

## 8. Headers and Broker Limitations

Spring's `MessageHeaders` can hold many value types, but brokers cannot necessarily transport all of them. Binders typically convert headers into representations supported by the broker. Mapping capabilities, allowed header lists, and encoding rules differ across Kafka, RabbitMQ, and Pulsar.

Points to verify:

- Kafka stores headers as byte key/value pairs; the binder may convert values and apply header mapping policies.
- RabbitMQ supports a header property table with AMQP-supported data types; some custom Java types cannot be transferred directly.
- Pulsar has key/value message properties; values typically need string representations or forms supported by the binder.
- Brokers and infrastructure impose limits on message or metadata size. Large headers increase storage, network, and logging overhead and can cause publishing failures.
- Internal framework or binder headers may handle routing and delivery. Do not rename or delete them without confirming the impact.

Never use headers to carry a large business payload. Primary data belongs in the payload; headers should contain only short metadata needed for identification, tracing, classification, or routing.

## 9. Combining with Supplier, Function, and Consumer

A `Supplier` typically creates new messages and can attach metadata upon emission. The example below reuses the `OrderCreated` record declared earlier:

~~~java
import java.util.UUID;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
class OrderSourceConfiguration {

    @Bean
    Supplier<Message<OrderCreated>> orderSource() {
        return () -> MessageBuilder.withPayload(
                        new OrderCreated("ORD-2001", "CUST-02"))
                .setHeader("eventId", UUID.randomUUID().toString())
                .setHeader("eventType", "OrderCreated")
                .setHeader("schemaVersion", 1)
                .build();
    }
}
~~~

A `Function` can read and transform the payload while keeping or updating metadata as shown in earlier examples. A `Consumer` usually only reads the payload and the headers needed for processing:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration
class AuditConfiguration {

    @Bean
    Consumer<Message<OrderValidated>> auditOrder() {
        return message -> {
            String eventId = (String) message.getHeaders().get("eventId");
            String correlationId =
                    (String) message.getHeaders().get("correlationId");

            System.out.printf(
                    "event=%s correlation=%s order=%s%n",
                    eventId,
                    correlationId,
                    message.getPayload().orderId());
        };
    }
}
~~~

When a `Consumer` does not emit a new message, it does not need to rebuild headers. If a `Consumer` forwards a message through another producer, construct the output message with an explicit header retention policy rather than passing through the entire input metadata verbatim.

## 10. Testing Header Policies

Tests should verify kept headers, updated headers, and removed headers. You can test a `Function` directly with JUnit:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class OrderHeaderTransformationTest {

    @Test
    void keepsUpdatesAndRemovesExpectedHeaders() {
        Message<OrderCreated> input = MessageBuilder
                .withPayload(new OrderCreated("ORD-3001", "CUST-03"))
                .setHeader("correlationId", "corr-123")
                .setHeader("eventType", "OrderCreated")
                .setHeader("internal-debug", "temporary")
                .build();

        OrderValidated payload = new OrderValidated(
                input.getPayload().orderId(),
                input.getPayload().customerId(),
                "VALIDATED",
                Instant.parse("2025-01-01T10:00:00Z"));

        Message<OrderValidated> output = MessageBuilder
                .withPayload(payload)
                .copyHeaders(input.getHeaders())
                .setHeader("eventType", "OrderValidated")
                .setHeader("schemaVersion", 2)
                .removeHeader("internal-debug")
                .build();

        assertEquals("corr-123", output.getHeaders().get("correlationId"));
        assertEquals("OrderValidated", output.getHeaders().get("eventType"));
        assertEquals(2, output.getHeaders().get("schemaVersion"));
        assertFalse(output.getHeaders().containsKey("internal-debug"));
        assertNull(input.getHeaders().get("schemaVersion"));
    }
}
~~~

This example focuses on verifying the header policy. In a real project, place transformation logic inside a `Function` bean and test that bean or use the Spring Cloud Stream test binder to verify messages across bindings. Integration tests with a real broker remain necessary if the application relies on header mapping, native headers, or binder-specific routing attributes.

## 11. Decision Workflow for Which Headers to Forward

Before emitting a message after transformation, apply the following workflow:

1. List existing headers and identify which component created each one: application, Spring, binder, or broker.
2. Keep correlation ID and trace context if they still describe the same processing flow.
3. Update `eventType`, `schemaVersion`, and `contentType` to match the output payload.
4. Remove temporary headers, sensitive headers, or headers meaningful only in the prior hop.
5. For messages arriving from untrusted sources or crossing service boundaries, use an allowlist of permitted headers.
6. Check serialization capabilities, size limits, and binder mapping policies.
7. Write tests asserting which headers must be kept, updated, and removed.

Headers are metadata accompanying the payload, and each header has an owner and a scope of use. Keeping headers preserves context; adding or updating headers accurately describes the new event; removing headers prevents carrying stale or unauthorized data forward. Managing these three operations intentionally makes message flows in Spring Cloud Stream easier to trace, safer, and more consistent.

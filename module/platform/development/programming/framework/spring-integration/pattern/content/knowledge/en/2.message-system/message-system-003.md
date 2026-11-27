# MessageBuilder and intentional message construction

## 1. Context and objectives

In the **Message system** chapter of the **SPRING_INTEGRATION_PATTERN** module, a processing flow is built from components exchanging messages over channels. This is the foundation for implementing **Enterprise Integration Patterns** with Spring Integration: Router decides the branch, Filter discards unsuitable messages, Transformer converts data, Splitter/Aggregator handles message groups, Gateway connects business code with messaging, and retry and error channels help manage failures. For components to stay loosely coupled and easy to test, incoming messages must be constructed with clear intent.

**MessageBuilder** is the tool for creating a **Message** object consisting of business data (*payload*) and accompanying information (*headers*). “Intentional message construction” means proactively determining:

1. **What data** truly needs to be sent?
2. **What metadata** does downstream need for routing, correlation, observability, and processing?
3. **What metadata should not be propagated** because it is expired, unnecessary, or sensitive?
4. **Who is responsible** for setting header values and keeping them consistent?

After this lesson, you will be able to create new messages, add or remove headers, create derived messages without mutating old ones, choose a header-copying policy, and verify behavior with JUnit.

## 2. What is a Message and why do we need a builder?

Spring Messaging defines the general interface:

~~~java
public interface Message<T> {
    T getPayload();
    MessageHeaders getHeaders();
}
~~~

| Component | Role | Example |
| --- | --- | --- |
| Payload | Main data processed by consumers | Order record, text string, byte array |
| Business header | Context for consumers to understand or decide processing | tenantId, eventType, schemaVersion |
| Integration header | Metadata serving messaging mechanisms | id, timestamp, replyChannel, errorChannel, correlationId |
| MessageChannel | Channel transferring messages between producers and consumers | DirectChannel, QueueChannel, PublishSubscribeChannel |

A **Message** object has no methods to reset payload or headers after creation. The **MessageHeaders** map is read-only: calling put/remove on it can throw **UnsupportedOperationException**. This is a contract preventing components from accidentally altering the structure of a message that another component is using.

However, **immutability here applies only to the message structure and header map**. If the payload contains a mutable object such as an ArrayList, or a header value is a mutable Map, the contents inside those objects can still be mutated via shared references. Prefer records, immutable objects, or defensive copies when concurrent processing is needed.

You can instantiate **GenericMessage** directly, but MessageBuilder expresses the intent of adding headers, copying context, and creating derived messages much more clearly.

~~~mermaid
flowchart LR
    P["Business payload"] --> B["MessageBuilder"]
    H["Intentional headers"] --> B
    B --> M["Structurally immutable Message<T>"]
    M --> C["MessageChannel"]
    C --> F["Filter / Router / Transformer / Gateway"]
~~~

## 3. Creating a new message from a payload

The example uses **org.springframework.integration.support.MessageBuilder**, Spring Integration's default message builder. The Spring ecosystem also has **org.springframework.messaging.support.MessageBuilder**; pick the right import for the API you use, especially when you need Spring Integration-specific convenience methods like setCorrelationId or setPriority.

~~~java
import java.math.BigDecimal;

import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

record OrderPlaced(String orderId, String customerId, BigDecimal total) {}

OrderPlaced event = new OrderPlaced(
        "ORD-2026-001",
        "CUS-007",
        new BigDecimal("125000.00")
);

Message<OrderPlaced> message = MessageBuilder.withPayload(event)
        .setHeader("eventType", "order.placed")
        .setHeader("tenantId", "tenant-hcm")
        .setHeader("schemaVersion", 1)
        .setHeader("traceId", "trace-abc-123")
        .setCorrelationId(event.orderId())
        .build();

OrderPlaced payload = message.getPayload();
String tenant = message.getHeaders().get("tenantId", String.class);
Object correlation = message.getHeaders().get("correlationId");
~~~

Reading the example in order: **withPayload** sets the primary data, **setHeader** adds metadata for consumers, **setCorrelationId** assigns the key linking messages belonging to the same order, and **build** produces the message to send through a channel. The tenantId and traceId values in the example must come from authenticated context in real deployments; do not invent default values for every request.

The payload must be non-**null**. If you need to represent the absence of data, use an appropriate model type or a business message with an explicit status; do not treat passing null as a normal message.

### When to use payload, when to use headers?

A useful rule of thumb: **payload answers “what needs to be processed?”, while headers answer “in what context is it processed?”**.

| Information | Where should it go? | Reason |
| --- | --- | --- |
| Order ID, amount, line items | Payload | Primary business data |
| Event type for Router branching | Header or payload type, depending on contract | Enables routing without needing to know detailed payload structure |
| Authenticated tenant | Header if it is cross-flow context | Needed by many handlers, but must be ensured unforgeable |
| Trace ID | Header | Serves observability and log correlation |
| Passwords, access tokens, card details | Do not put arbitrarily into exchange/log headers | Avoid leakage during tracing, serialization, or adapter transit |
| UUID identifying a single message | Framework-generated id header | Must not be confused with order ID or correlation ID |

Custom header names should follow a consistent convention; for example **tenantId**, **eventType**, **schemaVersion**, **traceId**. It is best to group header names into constants so producers and consumers do not diverge in spelling:

~~~java
final class OrderHeaders {
    static final String EVENT_TYPE = "eventType";
    static final String TENANT_ID = "tenantId";
    static final String SCHEMA_VERSION = "schemaVersion";
    static final String TRACE_ID = "traceId";

    private OrderHeaders() {}
}
~~~

## 4. Controlling headers explicitly

MessageBuilder supports the key operations:

| API | Behavior | When to use |
| --- | --- | --- |
| withPayload(value) | Starts a new message with the chosen payload | New event, transformation result |
| fromMessage(source) | Starts from payload and headers of an existing message | Adding context while keeping the payload |
| setHeader(name, value) | Sets or replaces a header value; a null value can remove a header | Tagging completed processing |
| setHeaderIfAbsent(name, value) | Sets only if the header does not already have a value | Setting defaults without overwriting upstream |
| removeHeader(name) | Removes a header in the created message | Stripping temporary context |
| removeHeaders(patterns...) | Removes headers matching supported names/patterns | Cleaning up a group of headers |
| copyHeaders(map) | Copies and may overwrite headers with matching names | Need metadata from the input message |
| copyHeadersIfAbsent(map) | Copies only headers not yet present in the builder | Preserving priority for already set values |
| build() | Creates the complete Message object | Sending to a channel |

### 4.1. Creating a derived message with the same payload

~~~java
Message<OrderPlaced> reviewed = MessageBuilder.fromMessage(message)
        .setHeaderIfAbsent("sourceSystem", "checkout")
        .setHeader("validated", true)
        .removeHeader("debugOnly")
        .build();

// The input message retains its original header values.
// The new message has header validated = true.
~~~

**fromMessage** is appropriate when only changing interpretation/metadata. It creates a new message and does not directly mutate the passed-in message. Although the payload is reused, if the payload is a mutable object both messages can still share that same object.

### 4.2. Changing the payload type and choosing headers to forward

Example of a Transformer normalizing an event into data for accounting:

~~~java
record InvoiceCommand(String orderId, BigDecimal amount) {}

Message<OrderPlaced> incoming = message;
OrderPlaced order = incoming.getPayload();

InvoiceCommand command =
        new InvoiceCommand(order.orderId(), order.total());

Message<InvoiceCommand> outgoing =
        MessageBuilder.withPayload(command)
                .copyHeaders(incoming.getHeaders())
                .removeHeader("debugOnly")
                .removeHeader("temporaryRoutingHint")
                .setHeader("eventType", "invoice.requested")
                .setHeader("processedBy", "invoice-transformer")
                .build();
~~~

**withPayload** is the right choice when the payload changes from OrderPlaced to InvoiceCommand: **fromMessage** is not intended for changing payload types. With **copyHeaders**, forwarded headers must still retain valid semantics. For instance, the old eventType order.placed should be updated to invoice.requested; and a routing hint valid only at the prior stage should be removed.

Pay attention to ordering:

~~~java
Message<String> result = MessageBuilder.withPayload("normalized")
        .setHeader("origin", "current")
        .copyHeadersIfAbsent(incoming.getHeaders())
        .build();
~~~

In this example, **origin=current** is preserved if incoming has a different origin header. Replacing **copyHeadersIfAbsent** with **copyHeaders** in the same spot lets the incoming value overwrite the origin just set. When you want new values to take precedence, you can also copy first and call **setHeader** afterward.

### 4.3. Standard headers and data types

Not every header is a String:

| Standard header | Typical value | What to remember |
| --- | --- | --- |
| MessageHeaders.ID | UUID | Created by the framework; do not overwrite manually |
| MessageHeaders.TIMESTAMP | Long | Message creation timestamp; do not overwrite manually |
| MessageHeaders.REPLY_CHANNEL | MessageChannel or channel name | Set only when there is actually a request/reply flow |
| MessageHeaders.ERROR_CHANNEL | MessageChannel or channel name | Routes certain messaging errors; does not replace exception handling at all layers |
| IntegrationMessageHeaderAccessor.CORRELATION_ID | Object | Key linking messages sharing a transaction/group |
| IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER | Integer | Element order within the group |
| IntegrationMessageHeaderAccessor.SEQUENCE_SIZE | Integer | Total number of elements in the group if known |
| IntegrationMessageHeaderAccessor.PRIORITY | Integer | Takes priority effect only when channel/consumer supports it, e.g., PriorityChannel |

**ID** represents *a single message instance*, while **correlationId** represents a *business relationship* among multiple messages. For example, the same order has “placed”, “paid”, and “shipped” messages: they should have distinct message IDs, yet can share a correlationId if a flow needs to link them.

~~~java
Message<String> first = MessageBuilder.withPayload("item-1")
        .setCorrelationId("BATCH-42")
        .setSequenceNumber(1)
        .setSequenceSize(2)
        .build();

Message<String> second = MessageBuilder.withPayload("item-2")
        .setCorrelationId("BATCH-42")
        .setSequenceNumber(2)
        .setSequenceSize(2)
        .build();
~~~

The sequenceNumber/sequenceSize pair is only meaningful when producer and downstream agree on a grouping mechanism, such as for an Aggregator to assemble the two items correctly. If a Splitter in the flow manages the corresponding headers itself, respect the rules applied by the Splitter and avoid setting conflicting values manually.

**ID and timestamp are read-only headers.** Do not use setHeader to fix MessageHeaders.ID or MessageHeaders.TIMESTAMP, and do not rely on them being copied verbatim from a previous message. When creating a new message, the framework manages the identity/timestamp of the new message. If you need a durable identifier across multiple steps, declare a separate business header like orderId/correlationId.

## 5. Sending messages into a Spring Integration flow

Intentional message construction helps endpoints operate under a clear contract:

~~~mermaid
flowchart LR
    A["Order API"] --> B["MessageBuilder"]
    B --> C["orderInputChannel"]
    C --> D{"Filter: valid?"}
    D -->|Yes| E{"Router: eventType"}
    D -->|No| X["Discard / report error per design"]
    E -->|order.placed| F["Transformer: InvoiceCommand"]
    E -->|order.cancelled| G["Cancel handler"]
    F --> H["Outbound adapter"]
~~~

Example of a producer sending events into a Spring-configured channel:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.stereotype.Component;

@Component
public class OrderEventPublisher {
    private final MessageChannel orderInputChannel;

    public OrderEventPublisher(
            @Qualifier("orderInputChannel") MessageChannel orderInputChannel) {
        this.orderInputChannel = orderInputChannel;
    }

    public void publish(OrderPlaced order, String tenantId, String traceId) {
        if (order == null || tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Missing order or tenantId");
        }

        Message<OrderPlaced> event = MessageBuilder.withPayload(order)
                .setHeader(OrderHeaders.EVENT_TYPE, "order.placed")
                .setHeader(OrderHeaders.TENANT_ID, tenantId)
                .setHeader(OrderHeaders.TRACE_ID, traceId)
                .setCorrelationId(order.orderId())
                .build();

        boolean accepted = orderInputChannel.send(event);
        if (!accepted) {
            throw new IllegalStateException("Channel did not accept the message");
        }
    }
}
~~~

In a real application, you need an **orderInputChannel** bean and at least one appropriate endpoint to receive messages according to the chosen channel type. The send method returns a boolean, but can also throw an exception due to configuration or downstream processing failures, especially with a synchronous DirectChannel. A successful send **does not automatically mean data was durably persisted or successfully processed across the entire system**.

Consumers can read headers without depending on the publisher class:

~~~java
import org.springframework.messaging.Message;

void handle(Message<OrderPlaced> incoming) {
    OrderPlaced order = incoming.getPayload();
    String tenant = incoming.getHeaders().get("tenantId", String.class);
    String eventType = incoming.getHeaders().get("eventType", String.class);

    // Check tenant, eventType, and process corresponding business logic.
}
~~~

When a handler returns only a **payload**, message-producing endpoints usually propagate input headers. When a **Transformer** returns a full Message, the Transformer is responsible for the headers of the returned message; do not implicitly assume all input headers will be preserved. Some adapters or endpoints have their own propagation rules, so verify the contract of the endpoint you are using.

## 6. Designing headers for Router, Aggregator, retry, and error handling

MessageBuilder creates metadata; **it does not implement** the patterns itself. Metadata takes effect only when a component in the flow processes it.

**Router:** Can read eventType for branching, but must define the valid value set and behavior for unrecognized event types. If eventType originates from external input, normalize/validate it before using it to route to sensitive paths.

**Filter:** Headers like tenantId and schemaVersion can help select conditions, but Filter does not replace authentication or authorization. Caller-supplied headers are untrusted until validated at system boundaries.

**Transformer:** When changing payload, use withPayload and an explicit copyHeaders policy. Reset eventType/schemaVersion if the new content carries a different meaning or contract.

**Splitter/Aggregator:** Fields correlationId, sequenceNumber, sequenceSize must be consistent and match the grouping scheme. Avoid using MessageHeaders.ID as a group key; ID changes when creating derived messages.

**Gateway/reply channel:** ReplyChannel should be declared in request/reply flows needing a response, not attached by default to every fire-and-forget event. A channel specified by name must actually resolve at runtime.

**Retry/error channel:** The errorChannel header can participate in error routing under Spring Integration mechanisms, yet where an exception is sent still depends on the endpoint, executor, error handling, and gateway configuration. Do not try to create retries merely by setting an arbitrary header: you need advice or adapter retry mechanisms, paired with idempotency principles to avoid duplicate processing.

**Observability:** traceId helps connect logs across hops. Only log necessary metadata; avoid logging entire messages if payload/headers contain sensitive data. In practice, you also need to propagate trace context matching the observability tool in use.

## 7. Testing message creation behavior

You do not need to run the entire application to test the MessageBuilder contract. The example below uses **JUnit 5** and an in-process **DirectChannel** with a subscriber receiving the message immediately:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

class MessageBuilderExampleTest {

    @Test
    void buildsAndSendsMessageWithExplicitHeaders() {
        Message<String> original = MessageBuilder.withPayload("ORD-42")
                .setHeader("eventType", "order.placed")
                .setCorrelationId("ORD-42")
                .build();

        DirectChannel channel = new DirectChannel();
        AtomicReference<Message<?>> received = new AtomicReference<>();
        channel.subscribe(received::set);

        assertTrue(channel.send(original));
        assertSame(original, received.get());
        assertEquals("order.placed",
                received.get().getHeaders().get("eventType"));
        assertEquals("ORD-42", received.get().getPayload());
    }

    @Test
    void derivedMessageRetainsOriginalHeadersButCanOverrideThem() {
        Message<String> original = MessageBuilder.withPayload("pending")
                .setHeader("eventType", "order.placed")
                .setHeader("stage", "created")
                .build();

        Message<String> derived = MessageBuilder.fromMessage(original)
                .setHeader("stage", "validated")
                .removeHeader("eventType")
                .build();

        assertEquals("created", original.getHeaders().get("stage"));
        assertEquals("order.placed", original.getHeaders().get("eventType"));
        assertEquals("validated", derived.getHeaders().get("stage"));
        assertFalse(derived.getHeaders().containsKey("eventType"));
        assertNotEquals(original.getHeaders().getId(),
                derived.getHeaders().getId());
    }
}
~~~

These tests prove: the message is sent into the channel, headers hold the expected values, and the derived message does not mutate the old headers and gets a new ID. These are local unit test examples; when integrating into an application, you must also test actual routes, downstream failures, serialization, and behavior per channel type.

## 8. Common design mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Stuffing everything into headers | Message is hard to understand, leaks info, and adds transit cost | Include only metadata downstream genuinely needs |
| Using message ID as transaction ID | Loses stable linkage when new messages are created | Use a separate orderId/correlationId |
| Assuming Message is deeply immutable | Mutable payload/header values can still be modified | Use immutable types or defensive copies |
| Copying all headers without checking meaning | Routing hints, debug flags, or stale context leak to new steps | Selectively keep, remove, or replace stale headers |
| Assuming copyHeadersIfAbsent overwrites | Old/already-set values take unexpected precedence | Specify order of copying and setting headers clearly |
| Setting priority without PriorityChannel | Processing order does not change | Choose a channel/consumer that actually supports priority |
| Setting id/timestamp manually | Wrong reliance on framework-managed headers | Let the framework generate them; use an independent business key |
| Assuming send returning true means processing finished | Missed failures or lost data in later hops | Design proper acknowledgments, transactions, and retries |
| Hardcoding non-existent reply/error channel names | Runtime fails to route as intended | Configure real channels and test error paths |
| Not validating external tenantId | Could process data for the wrong tenant | Validate context at boundaries and check in necessary consumers |

## 9. Hands-on exercise: designing messages for a shipping system

Suppose an application receives a **shipment.created** event from an API, after which a Router directs it to an intra-city or inter-province delivery branch. Each shipment has shipmentId, destinationProvince, and packageWeight; the system also needs tenantId, traceId, and schema version.

**Requirements:**

1. Create a ShipmentCreated record containing the three business fields.
2. Use MessageBuilder to create a Message with eventType, tenantId, traceId, schemaVersion.
3. Use shipmentId as the correlationId to link with subsequent shipping events.
4. Create a derived message after the validation step with header validated=true; preserve the original message.
5. When converting the payload to a DispatchCommand record, copy only still-valid headers and update eventType to dispatch.requested.

A sample solution for creation and derivation:

~~~java
record ShipmentCreated(String shipmentId, String destinationProvince,
                       double packageWeight) {}
record DispatchCommand(String shipmentId, String routeCode) {}

ShipmentCreated shipment =
        new ShipmentCreated("SHP-42", "Ho Chi Minh", 2.5);

Message<ShipmentCreated> created = MessageBuilder.withPayload(shipment)
        .setHeader("eventType", "shipment.created")
        .setHeader("tenantId", "tenant-hcm")
        .setHeader("traceId", "trace-42")
        .setHeader("schemaVersion", 1)
        .setCorrelationId(shipment.shipmentId())
        .build();

Message<ShipmentCreated> validated = MessageBuilder.fromMessage(created)
        .setHeader("validated", true)
        .build();

DispatchCommand dispatch =
        new DispatchCommand(shipment.shipmentId(), "HCM-INTRA");

Message<DispatchCommand> requested =
        MessageBuilder.withPayload(dispatch)
                .copyHeaders(validated.getHeaders())
                .removeHeader("validated")
                .setHeader("eventType", "dispatch.requested")
                .build();
~~~

When extending the exercise, determine routeCode via real routing logic instead of hardcoding, validate positive packageWeight, validate tenantId, and write a test proving created still retains eventType=shipment.created after requested is created. If sending the message over a broker, verify the converter supports the payload type and every header value type.

## 10. Checklist before publishing a message

- Payload has a clear type and business meaning; required values have been validated.
- Headers contain only necessary metadata; names and data types agree between producer/consumer.
- Correlation ID reflects the business lifecycle properly; not confused with message ID.
- No attempts to alter framework-managed ID/timestamp.
- When creating derived messages, precedence of setHeader, copyHeaders, copyHeadersIfAbsent, and headers to remove have been reviewed.
- No tokens, passwords, or sensitive data placed in headers that could be logged or forwarded to other systems.
- Tests exist for created messages, key headers, immutability of the original message, and actual routing flows.

**Practical principle:** a good message lets its receiver know *what data it carries*, *in what context it should be processed*, and *which metadata must be kept for the next step*. MessageBuilder helps enforce that contract at the boundary between Spring Integration components.

## References

- [Spring Integration Reference — Message](https://docs.spring.io/spring-integration/reference/message.html): Message, MessageHeaders, MessageBuilder, propagation, and standard headers.
- [Spring Integration API — MessageBuilder](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/support/MessageBuilder.html): API for creating messages from a payload or an existing message.
- [Spring Framework — Messaging](https://docs.spring.io/spring-framework/reference/integration.html): General concepts of Message and MessageChannel.

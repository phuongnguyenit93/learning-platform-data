# Event Types and Payload Mapping in the Spring Integration Event Adapter

## Lesson Objectives

In the **Event Adapter** chapter of the **SPRING_INTEGRATION_ADAPTERS** module, we connect the Spring `ApplicationEvent` mechanism with `MessageChannel`. This lesson addresses two questions that are easily confused when designing a message contract:

1. **Event type:** which event types does the adapter receive/emit, and is that type determined at the Spring boundary or inside Spring Integration?
2. **Payload mapping:** what data becomes `Message.getPayload()`, when does it need conversion to a domain object, and how are headers preserved?

After this lesson, you will be able to configure `eventTypes` on the inbound event adapter, understand the precedence order when mapping event sources to messages, use `publishPayload` on the outbound adapter, write transformers to normalize payloads, and verify special cases such as `MessagingEvent` and `PayloadApplicationEvent`.

The scope here is event exchange **within a Spring `ApplicationContext`**. Spring Integration also has adapters for files, SFTP, HTTP, JMS, AMQP, Kafka, and databases; the event adapter mechanism helps connect internal components before or after those connections, without providing a durable queue or cross-process communication on its own.

## 1. Three Data Type Layers Not to Equate

~~~mermaid
flowchart LR
    A["Spring ApplicationEventPublisher"] -->|"ApplicationEvent or POJO"| B["Inbound event adapter"]
    B -->|"Message&lt;T&gt;"| C["MessageChannel"]
    C --> D["Transformer / Filter / Router"]
    D -->|"Message&lt;DomainEvent&gt;"| E["Outbound event adapter"]
    E -->|"Spring event"| F["@EventListener / ApplicationListener"]
~~~

The diagram involves three concepts:

| Concept | Role | Example |
| --- | --- | --- |
| **Spring event type** | The type `ApplicationEventPublisher` publishes and Spring listeners classify | `OrderApprovedApplicationEvent`, `PayloadApplicationEvent<OrderApproved>`, `MessagingEvent` |
| **Spring Integration message type** | The `Message<?>` envelope carrying payload and headers over `MessageChannel` | `Message<OrderApprovedApplicationEvent>`, `Message<OrderApproved>` |
| **Domain payload type** | The business contract used by components inside the flow | `OrderApproved(String orderId, BigDecimal total, Instant approvedAt)` |

For example, `OrderApprovedApplicationEvent` is a Spring event type, but after passing through a transformer, the message payload can become `OrderApproved`. Filtering by event type happens at **the entry boundary**; filtering by `orderId` or `total` belongs to business logic **inside the flow**. These two operations address two different layers.

## 2. Inbound Adapter: Event Type Determines Which Events Are Received

`ApplicationEventListeningMessageProducer` (package `org.springframework.integration.event.inbound`) is an inbound channel adapter that also acts as a Spring application listener. The adapter receives events published by `ApplicationEventPublisher` and sends messages to an output channel.

By default, it can receive all matching application events in the context. You can restrict it using `setEventTypes(Class<?>... eventTypes)`, corresponding to the `event-types` attribute in XML.

~~~java
@Bean
public ApplicationEventListeningMessageProducer approvedEventInbound(
        @Qualifier("rawOrderEvents") MessageChannel outputChannel) {

    var adapter = new ApplicationEventListeningMessageProducer();
    adapter.setEventTypes(OrderApprovedApplicationEvent.class);
    adapter.setOutputChannel(outputChannel);
    return adapter;
}
~~~

The configuration above sends only events matching `OrderApprovedApplicationEvent` into the `rawOrderEvents` channel. Spring lifecycle events such as `ContextRefreshedEvent` will not enter this channel.

**An easily overlooked point:** since Spring Framework 4.2, Spring allows `publishEvent(Object)` with plain POJOs. Spring uses `PayloadApplicationEvent` to wrap the POJO, and the Spring Integration inbound adapter supports filtering directly by the **POJO payload type**. Thus you can write:

~~~java
adapter.setEventTypes(OrderApproved.class);
~~~

when the publisher calls `publisher.publishEvent(new OrderApproved(...))`. The inbound adapter will send a message whose payload is `OrderApproved`. In this case, you do not need to write an `ApplicationListener<PayloadApplicationEvent<OrderApproved>>` manually.

`setEventTypes(...)` is **type-based filtering**, not property-value filtering. If you want to accept only orders with a positive total or a specific status, use a `Filter`, `Router`, or validation logic after the event is received.

## 3. Inbound Payload Mapping: Precedence Order

The inbound event adapter has three ways to determine the output payload or message. The processing order is an essential part of the integration contract.

| Data received from Spring | How inbound adapter creates the message | Key takeaway |
| --- | --- | --- |
| `ApplicationEvent` whose `getSource()` is a `Message<?>` | Forwards **the original message itself** to the output channel | Original message headers and payload are preserved; normal payload extraction branches are skipped |
| `PayloadApplicationEvent<T>` for a POJO | Extracts `event.getPayload()` as the message payload | Listeners can filter by `T.class`; original message headers do not appear automatically |
| Regular `ApplicationEvent`, source is not `Message<?>`, `payloadExpression` is set | Evaluates SpEL on the event object to obtain payload | Useful when only part of the event content is needed |
| Regular `ApplicationEvent`, source is not `Message<?>`, no `payloadExpression` | Uses the **event itself** as payload | Downstream transformers receive the event object, not `event.getSource()` |

In particular, **never assume the payload defaults to `event.getSource()`**. For a regular event without an expression configured, the payload is the **event**. For an event published from a `Message<?>`, the entire message can be preserved as-is. For a POJO payload event, Spring Integration extracts the POJO object. These three paths behave differently.

Example of a custom event:

~~~java
package com.example.orders;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;
import org.springframework.context.ApplicationEvent;

public final class OrderApprovedApplicationEvent extends ApplicationEvent {

    private final String orderId;
    private final BigDecimal total;
    private final Instant approvedAt;

    public OrderApprovedApplicationEvent(
            Object source, String orderId, BigDecimal total, Instant approvedAt) {
        super(source);
        this.orderId = Objects.requireNonNull(orderId);
        this.total = Objects.requireNonNull(total);
        this.approvedAt = Objects.requireNonNull(approvedAt);
    }

    public String getOrderId() {
        return orderId;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public Instant getApprovedAt() {
        return approvedAt;
    }
}
~~~

With this event and `eventTypes(OrderApprovedApplicationEvent.class)`, if no `payloadExpression` is set, the message payload after the inbound adapter is `OrderApprovedApplicationEvent`.

If only the order ID is needed, you can configure an **alternative option**:

~~~java
import org.springframework.expression.spel.standard.SpelExpressionParser;

// Set on the adapter before registering in the Spring context:
adapter.setPayloadExpression(
        new SpelExpressionParser().parseExpression("orderId"));
~~~

The expression `orderId` reads the property from `OrderApprovedApplicationEvent`, corresponding to getter `getOrderId()`. The output payload is then a `String`; downstream transformers or service activators must declare matching types. Do not add this configuration to the full-event normalization example in the next section, as it changes the flow's contract.

## 4. Complete Example: Filter by Event Type Then Normalize Payload

Problem: when the order processing system emits `OrderApprovedApplicationEvent`, we want to accept only this event type, convert it into the `OrderApproved` business contract, and hand it off to a consumer in Spring Integration.

**Step 1 — Define the target payload.**

`OrderApproved.java`:

~~~java
package com.example.orders;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderApproved(
        String orderId,
        BigDecimal total,
        Instant approvedAt) {
}
~~~

In the same package lies `OrderApprovedApplicationEvent` from Section 3.

**Step 2 — Declare the inbound adapter and two channels.**

`OrderEventAdapterConfig.java`:

~~~java
package com.example.orders;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.event.inbound.ApplicationEventListeningMessageProducer;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class OrderEventAdapterConfig {

    @Bean
    public MessageChannel rawOrderEvents() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel normalizedOrderEvents() {
        return new DirectChannel();
    }

    @Bean
    public ApplicationEventListeningMessageProducer approvedEventInbound(
            @Qualifier("rawOrderEvents") MessageChannel channel) {

        var adapter = new ApplicationEventListeningMessageProducer();
        adapter.setEventTypes(OrderApprovedApplicationEvent.class);
        adapter.setOutputChannel(channel);
        return adapter;
    }
}
~~~

**Step 3 — Convert the event into the domain payload and consume it.**

`OrderEventEndpoints.java`:

~~~java
package com.example.orders;

import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.annotation.Transformer;
import org.springframework.stereotype.Component;

@Component
public class OrderEventEndpoints {

    @Transformer(
            inputChannel = "rawOrderEvents",
            outputChannel = "normalizedOrderEvents")
    public OrderApproved toDomainPayload(OrderApprovedApplicationEvent event) {
        return new OrderApproved(
                event.getOrderId(),
                event.getTotal(),
                event.getApprovedAt());
    }

    @ServiceActivator(inputChannel = "normalizedOrderEvents")
    public void consume(OrderApproved event) {
        System.out.println("Approved order: " + event.orderId());
        // Example: forward to an appropriate HTTP, JMS, or Kafka adapter.
    }
}
~~~

`@Transformer` receives an `OrderApprovedApplicationEvent` payload and returns an `OrderApproved` payload. Spring Integration forwards that data in a message through `normalizedOrderEvents`. This normalization lets downstream steps depend on the business contract rather than directly on the Spring `ApplicationEvent` API.

**Step 4 — Publish the event from a Spring service.**

`OrderApprovalService.java`:

~~~java
package com.example.orders;

import java.math.BigDecimal;
import java.time.Instant;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderApprovalService {

    private final ApplicationEventPublisher publisher;

    public OrderApprovalService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void approve(String orderId, BigDecimal total) {
        publisher.publishEvent(new OrderApprovedApplicationEvent(
                this, orderId, total, Instant.now()));
    }
}
~~~

When `approve("ORD-2048", new BigDecimal("120.50"))` is called, the sequence is:

~~~mermaid
sequenceDiagram
    participant S as OrderApprovalService
    participant P as ApplicationEventPublisher
    participant I as Event inbound adapter
    participant C as rawOrderEvents
    participant T as Transformer
    participant O as normalizedOrderEvents
    participant H as Consumer

    S->>P: OrderApprovedApplicationEvent
    P->>I: event type matches
    I->>C: Message<OrderApprovedApplicationEvent>
    C->>T: event as payload
    T->>O: Message<OrderApproved>
    O->>H: OrderApproved
~~~

By default, `DirectChannel` and the standard Spring event multicaster operate synchronously. When combined with `@Async`, an executor channel, or a custom multicaster, consumer invocation timing and error reporting can change.

## 5. Publishing POJOs: Reducing Wrapper Layers

If you only need to pass pure business events, Spring lets you publish POJOs directly:

~~~java
publisher.publishEvent(new OrderApproved(
        "ORD-2049",
        new BigDecimal("75.00"),
        Instant.now()));
~~~

To receive this payload type directly, update the inbound configuration accordingly:

~~~java
adapter.setEventTypes(OrderApproved.class);
~~~

At the Spring boundary, the POJO event is represented via `PayloadApplicationEvent<OrderApproved>`. The inbound adapter recognizes the payload-style event and creates a message with payload `OrderApproved`. Because the payload is already normalized, you can attach the consumer directly to the output channel without converting `OrderApprovedApplicationEvent → OrderApproved`.

This is **an alternative design** to the example in Section 4. If you change `eventTypes` to `OrderApproved.class`, the old `@Transformer` expecting `OrderApprovedApplicationEvent` no longer fits. Update or remove the transformer so input and output types match.

| When you need | Recommended choice |
| --- | --- |
| A Spring event carrying extra source, timestamp, context, and its own API | Event class extending `ApplicationEvent` |
| Business events as an independent contract where all parties know the POJO type | Publish and receive the POJO via `publishEvent(Object)` |
| Preserving `Message<?>` and headers like `correlationId`, `traceId` | Wrap the message with `MessagingEvent` or design an event contract with explicit metadata |

There is no single choice for every system; the contract must fit downstream needs.

## 6. Outbound Mapping: From Message Back to Spring Event

`ApplicationEventPublishingMessageHandler` is the outbound adapter in the same `spring-integration-event` module. It turns a message inside Spring Integration into an event for `ApplicationEventPublisher`.

The event publishing rules are:

| Payload in input message | `publishPayload` | Event received by Spring |
| --- | --- | --- |
| `OrderApprovedApplicationEvent` (already extends `ApplicationEvent`) | `false` or `true` | `OrderApprovedApplicationEvent` itself |
| `OrderApproved` (POJO) | `false` (default) | `MessagingEvent` wrapping the full `Message<OrderApproved>` |
| `OrderApproved` (POJO) | `true` | `OrderApproved` published directly; Spring may represent it as `PayloadApplicationEvent<OrderApproved>` |

Example outbound endpoint publishing a POJO:

~~~java
@Bean
@ServiceActivator(inputChannel = "outboundOrderEvents")
public ApplicationEventPublishingMessageHandler outboundOrderEventPublisher() {
    var handler = new ApplicationEventPublishingMessageHandler();
    handler.setPublishPayload(true);
    return handler;
}
~~~

This example assumes a `MessageChannel` bean named `outboundOrderEvents` already exists and a producer sends `Message<OrderApproved>` to it. A listener can handle it:

~~~java
@EventListener
public void onApproved(OrderApproved event) {
    System.out.println("Observed: " + event.orderId());
}
~~~

Without calling `setPublishPayload(true)`, the listener above will not directly receive `OrderApproved` from a message with a POJO payload; in that case listen for `MessagingEvent`, for example:

~~~java
@EventListener
public void onMessagingEvent(MessagingEvent event) {
    var message = event.getMessage();
    Object correlationId = message.getHeaders().get("correlationId");

    if (message.getPayload() instanceof OrderApproved approved) {
        System.out.println(approved.orderId() + ", corr=" + correlationId);
    }
}
~~~

The second listener requires importing `org.springframework.integration.event.core.MessagingEvent`. The two options depend on your `publishPayload` choice; do not apply both and expect a single event to automatically be duplicated.

## 7. Header Mapping and Metadata

**Payload mapping is not header mapping.** `Message<?>` and `ApplicationEvent` have two different metadata models.

- When the inbound adapter receives an event whose `getSource()` is a `Message<?>`, it forwards the original message, so headers like `correlationId` and `traceId` can survive across this boundary.
- When receiving a regular Spring event or a POJO, the inbound adapter creates a new message. It cannot reconstruct headers of a message that never existed at the source; put important data into the event structure or add headers after receiving.
- When the outbound handler emits a `MessagingEvent`, Spring listeners can retrieve the original message via `getMessage()`. When publishing a POJO directly, message headers do not automatically become fields on the POJO.

Example intentionally preserving headers via `MessagingEvent`:

~~~java
import org.springframework.integration.event.core.MessagingEvent;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderApproved> original = MessageBuilder
        .withPayload(new OrderApproved(
                "ORD-2050", new BigDecimal("88.00"), Instant.now()))
        .setHeader("correlationId", "trace-2050")
        .build();

publisher.publishEvent(new MessagingEvent(original));
~~~

An inbound adapter filtering `MessagingEvent.class` can forward `original` itself to the output channel; downstream components can still read `correlationId`. This differs from publishing a POJO directly. Also distinguish business headers that must be preserved from internal Spring Integration headers (such as `id` or `timestamp`), which follow their own generation/update rules when a new message is created.

In systems with audit requirements, design an explicit event contract specifying `eventId`, `eventType`, `occurredAt`, `aggregateId`, `correlationId`, and `schemaVersion` when actually needed. Do not let consumers rely on a header happening to pass across the Spring event boundary.

## 8. Type Filtering, Content Filtering, and Routing

A common mistake is using type-filter configuration as a substitute for business rules. Split this into three steps:

1. **Filter event classes at the inbound adapter:** `setEventTypes(OrderApprovedApplicationEvent.class)` or `setEventTypes(OrderApproved.class)` to prevent unrelated events from entering the flow.
2. **Normalize payload:** use `@Transformer` to standardize on a DTO or record. Validate required fields such as `orderId`, `total`, and `approvedAt`.
3. **Business filtering/routing:** use a `Filter`, `Router`, or service activator to decide which orders need processing and which events go to HTTP/JMS/Kafka or storage.

Example business rule for `OrderApproved`: only events with `total.signum() > 0` are sent to the payment process. This rule does not belong in `eventTypes` because both valid and invalid events share the same `OrderApproved` class.

Another limitation: Java class names are an internal contract within the same JVM; when pushing messages to a broker or another service, define explicit schemas, content types, versioning, and serialization/deserialization mechanisms. Do not expose a Spring `ApplicationEvent` object directly as a public service schema if consumers only need domain data.

## 9. Common Errors Caused by Mismatched Mapping

| Symptom | Likely Cause | Check / Fix |
| --- | --- | --- |
| Inbound adapter does not push messages to channel | `eventTypes` filters the wrong class; event is a POJO but an `ApplicationEvent` class is filtered | Inspect the object passed to `publishEvent`; try `OrderApproved.class` or the exact event class |
| Transformer fails saying a method cannot be called on `String` | `payloadExpression="orderId"` was added while the transformer still expects an event object | Align the transformer parameter type with the new payload |
| Outbound `@EventListener(OrderApproved)` does not run | Payload is a POJO but `publishPayload=false`, so Spring receives `MessagingEvent` | Enable `setPublishPayload(true)` or change the listener to `MessagingEvent` |
| `correlationId` lost after crossing to Spring event | Published a POJO or a new event without message headers | Put the correlation ID in the event contract or use `MessagingEvent` to preserve the message |
| Reading payload mistakenly from `getSource()` | For regular `ApplicationEvent`, default inbound payload is the event, not the source | Use a transformer to extract fields or configure `payloadExpression` |
| An event runs multiple times or loops infinitely | Inbound adapter picks up the event published by the flow's own outbound adapter | Restrict types, separate directions, and avoid wiring back into the same publish cycle |

Specifically for `MessagingEvent`: the actual event type is `MessagingEvent`, while after the inbound adapter the payload reflects the original message. Therefore, when debugging, inspect **both the runtime event class before the adapter and the runtime message payload class after the adapter**.

## 10. Errors, Lifecycle, and Operational Limits

- **Synchronous boundary:** with the default configuration of `DirectChannel` and Spring's `ApplicationEventMulticaster`, listeners and the flow can execute on the thread publishing the event; downstream exceptions can affect the caller. The inbound adapter supports `errorChannel` to receive `MessagingException` in appropriate setups; do not assume all errors surface along the same path when using an executor or `@Async`.
- **Context lifecycle:** the inbound adapter is a component inside the Spring context; if you instantiate the object manually without registering it as a bean or running its lifecycle properly, you cannot expect it to receive events automatically.
- **Not durable:** Spring application events do not automatically persist, retry across restarts, guarantee cross-thread ordering, or provide exactly-once delivery. When reliable inter-service exchange is needed, combine JMS/AMQP/Kafka adapters with an appropriate delivery design.
- **Transactions:** events can be published before a database-writing transaction commits; if downstream must run after commit, consider a transaction-aware listener or an outbox, and verify the actual transaction context.
- **Loop prevention:** do not connect an event inbound flow to an outbound publisher that re-emits the exact event type the inbound adapter listens to, unless there is an explicit stopping condition.

## 11. Hands-On Verification Tests

Create a Spring Boot project with `spring-boot-starter-integration` and `spring-integration-event` dependencies (versions managed consistently by Spring Boot). Use `OrderApprovedApplicationEvent` and `OrderApproved` from the examples above, then run:

| Test case | Action | Expected result |
| --- | --- | --- |
| T1 — Correct type | Publish `OrderApprovedApplicationEvent("ORD-01", ...)` | Consumer receives `OrderApproved("ORD-01", ...)` |
| T2 — Wrong type | Publish `ContextRefreshedEvent` or another event class | No message enters the flow filtered for `OrderApprovedApplicationEvent.class` |
| T3 — POJO | Replace `eventTypes` with `OrderApproved.class`, remove unnecessary transformer, publish `OrderApproved` | Consumer receives payload of type `OrderApproved` |
| T4 — Mapping expression | Configure `payloadExpression` to extract `orderId` and update consumer to accept `String` | Consumer receives only the order ID |
| T5 — Headers | Publish `MessagingEvent` wrapping `Message<OrderApproved>` with `correlationId`, filter `MessagingEvent.class` | Message passing through inbound retains the same payload and header |
| T6 — Outbound mode | Send `Message<OrderApproved>` into outbound adapter, toggling `publishPayload` on/off | `OrderApproved` listener receives in `true` mode; `MessagingEvent` listener receives in default mode |
| T7 — Loop | Test a flow with inbound and outbound sharing the same event type | Flow has a guard preventing infinite re-publication |

When automating with JUnit, assert the **actual runtime type** of the payload, values of key fields, preserved headers, and consumer invocation counts. Logs displaying an object with an event-like name are not enough to prove the mapping is correct.

## 12. Self-Assessment Questions

1. Why is the event type `OrderApprovedApplicationEvent` not necessarily the payload type that the final consumer receives?
2. How does the inbound adapter behave when `ApplicationEvent.getSource()` is a `Message<?>`?
3. Why can `payloadExpression` make an existing `@Transformer` signature incompatible?
4. When `publishEvent(new OrderApproved(...))` is called, why can `setEventTypes(OrderApproved.class)` still be used?
5. If you need to preserve `traceId` from an integration flow to a Spring listener, do you choose `MessagingEvent` or publishing the POJO directly, and why?
6. When forwarding events to Kafka/JMS, which contract details should be placed intentionally into the payload or headers?

## References

- [Spring Integration Reference — Spring ApplicationEvent Support](https://docs.spring.io/spring-integration/reference/event.html): rules for `eventTypes`, `payloadExpression`, `PayloadApplicationEvent`, `MessagingEvent`, and `publishPayload`.
- [ApplicationEventListeningMessageProducer API](https://docs.spring.io/spring-integration/api/org/springframework/integration/event/inbound/ApplicationEventListeningMessageProducer.html).
- [ApplicationEventPublishingMessageHandler API](https://docs.spring.io/spring-integration/api/org/springframework/integration/event/outbound/ApplicationEventPublishingMessageHandler.html).
- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events).

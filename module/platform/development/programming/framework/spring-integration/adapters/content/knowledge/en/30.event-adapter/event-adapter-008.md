# Filtering Events Before Entering a Flow in Spring Integration

## Lesson Objectives

In the **Event Adapter** chapter of the **SPRING_INTEGRATION_ADAPTERS** module, `ApplicationEventListeningMessageProducer` brings **Spring `ApplicationEvent`s** into a `MessageChannel` for Spring Integration components to process. By default, an application emits many events unrelated to the business integration at hand, such as `ContextRefreshedEvent`, `ContextClosedEvent`, or events from other modules. If every event enters the same flow, handlers must check types themselves, raising the risk of type conversion errors and creating loops when combining inbound/outbound event adapters.

This lesson explains **filtering events before they enter a flow**, while clarifying the work that must happen *after* the entry point:

- Selecting the right **event type** at the inbound adapter with `setEventTypes(...)`.
- Distinguishing event-type filtering from filtering by **payload, headers, and business conditions** using `Filter`.
- Designing clear **accept**, **discard**, and **error** branches.
- Preventing accidental ingestion of lifecycle events, internal events, and events emitted by the application's own outbound adapter.
- Testing that non-matching events **do not enter the channel**, while valid events follow the intended path.

The scope is **Spring `ApplicationEvent` within the same `ApplicationContext`**. Spring Integration's HTTP, JMS, AMQP, Kafka, file, SFTP, and database adapters can share message-level `Filter`s, but you do not use the event adapter's `eventTypes` to filter Kafka records or HTTP messages.

## 1. Where Are Events Filtered Along the Data Path?

~~~mermaid
flowchart LR
    A["ApplicationEventPublisher"] --> B["Spring event multicaster"]
    B --> C{"Inbound event adapter\nmatches eventTypes?"}
    C -->|"No"| D["Ignore event"]
    C -->|"Yes"| E["Create/preserve Message<?>"]
    E --> F["input MessageChannel"]
    F --> G{"@Filter\nbusiness condition?"}
    G -->|"Pass"| H["Processing flow"]
    G -->|"Fail"| I["Discard channel\nor drop message"]
~~~

The two filtering points in the diagram **do not replace each other**.

| Location | Common criteria | Effect | Has a message entered the flow? |
| --- | --- | --- | --- |
| `ApplicationEventListeningMessageProducer.setEventTypes(...)` | Spring event class: `InvoicePaidEvent.class` | Blocks events outside the inbound contract | **Not yet**; non-matching events are not sent to the output channel |
| `@Filter` / `MessageFilter` after the channel | Payload properties, header values, business conditions | Lets valid messages proceed; drops or redirects rejected messages | **Yes**; message has already passed the inbound adapter |
| `@Router` / in-flow router | Payload type, business status, routing headers | Selects one or more processing branches | **Yes**; primary purpose is routing |
| Validation in service activator / transformer | Contract, required fields, data constraints | Reports errors or transforms data | **Yes**; validation failure differs from type-based filtering |

**Principle:** if a flow is meant only for certain application event types, filter at the **inbound adapter first**, then add a `Filter` for business conditions. Filtering by `eventTypes` does not replace validation or authorization.

## 2. What Is an Event Type?

For traditional Spring events, the type is a class extending `ApplicationEvent`:

~~~java
public final class InvoicePaidEvent extends ApplicationEvent {

    private final String invoiceId;

    public InvoicePaidEvent(Object source, String invoiceId) {
        super(source);
        this.invoiceId = invoiceId;
    }

    public String getInvoiceId() {
        return invoiceId;
    }
}
~~~

When calling:

~~~java
publisher.publishEvent(new InvoicePaidEvent(this, "INV-1001"));
~~~

The Spring multicaster distributes the event to matching listeners. The inbound adapter is also a Spring listener and can accept only `InvoicePaidEvent` by configuring:

~~~java
adapter.setEventTypes(InvoicePaidEvent.class);
~~~

Events of any other type are not sent into this adapter's `MessageChannel`. This is a **class-based filter**; it does not inspect `invoiceId` or payment status.

### Should You Accept Every ApplicationEvent Type?

An unrestricted configuration can feed Spring lifecycle events or events from other modules into your flow. If multiple types must be supported, specify the list explicitly:

~~~java
adapter.setEventTypes(
        InvoicePaidEvent.class,
        InvoiceCancelledEvent.class);
~~~

Here `InvoiceCancelledEvent` is another application-defined domain event class; the snippet illustrates declaring multiple types. If the two types have different data structures, the next step must **route/transform** by type rather than forcing both into `InvoicePaidEvent`.

When events inherit from a base class, understand the type-matching semantics of your Spring Integration version, especially with subclasses, interfaces, and POJOs wrapped by Spring into `PayloadApplicationEvent`. For clear contracts and easier testing, prefer concrete types at the adapter boundary.

## 3. Complete Example: Accept the Right Event, Then Check Business Rules

Problem: the system emits many events, but the accounting flow should receive only `InvoicePaidEvent`. Among received events, only invoices with an amount **greater than 0** advance to posting an accounting entry. Events of the right type with an invalid amount go to a discard branch for auditing.

The example uses Java 17+, Spring Boot, and Spring Integration.

**Gradle dependencies:**

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-integration")
    implementation("org.springframework.integration:spring-integration-event")
}
~~~

With Spring Boot, let Boot's dependency management choose compatible Spring Integration versions. The snippets below illustrate the application event path within the same JVM without calling an external accounting system yet.

### 3.1. Creating the Spring Event

`InvoicePaidEvent.java`:

~~~java
package com.example.billing;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;
import org.springframework.context.ApplicationEvent;

public final class InvoicePaidEvent extends ApplicationEvent {

    private final String invoiceId;
    private final BigDecimal amount;
    private final Instant occurredAt;

    public InvoicePaidEvent(
            Object source,
            String invoiceId,
            BigDecimal amount,
            Instant occurredAt) {
        super(source);
        this.invoiceId = Objects.requireNonNull(invoiceId);
        this.amount = Objects.requireNonNull(amount);
        this.occurredAt = Objects.requireNonNull(occurredAt);
    }

    public String getInvoiceId() {
        return invoiceId;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public Instant getOccurredAt() {
        return occurredAt;
    }
}
~~~

Placing the data to be exchanged directly in the event keeps the contract clear. `ApplicationEvent.getSource()` identifies the object publishing the event; do not assume it is the invoice ID or business payload.

### 3.2. Declaring the Inbound Adapter and Channels

`InvoiceEventAdapterConfig.java`:

~~~java
package com.example.billing;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.event.inbound.ApplicationEventListeningMessageProducer;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class InvoiceEventAdapterConfig {

    @Bean
    public MessageChannel rawInvoiceEvents() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel validInvoiceEvents() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel discardedInvoiceEvents() {
        return new DirectChannel();
    }

    @Bean
    public ApplicationEventListeningMessageProducer invoiceEventInbound(
            @Qualifier("rawInvoiceEvents") MessageChannel outputChannel) {

        var adapter = new ApplicationEventListeningMessageProducer();

        // Accept only the event type belonging to the accounting flow contract.
        adapter.setEventTypes(InvoicePaidEvent.class);

        // Only events passing the type filter reach this channel.
        adapter.setOutputChannel(outputChannel);

        return adapter;
    }
}
~~~

Here, `rawInvoiceEvents` is the boundary between Spring application events and Spring Integration. If Spring emits `ContextRefreshedEvent` or another business event, it will not enter `rawInvoiceEvents` through this adapter.

### 3.3. Filtering Amount and Branching Accept/Discard

`InvoiceEventEndpoints.java`:

~~~java
package com.example.billing;

import java.math.BigDecimal;
import org.springframework.integration.annotation.Filter;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class InvoiceEventEndpoints {

    @Filter(
            inputChannel = "rawInvoiceEvents",
            outputChannel = "validInvoiceEvents",
            discardChannel = "discardedInvoiceEvents")
    public boolean hasPositiveAmount(InvoicePaidEvent event) {
        return event.getAmount().compareTo(BigDecimal.ZERO) > 0;
    }

    @ServiceActivator(inputChannel = "validInvoiceEvents")
    public void createAccountingEntry(InvoicePaidEvent event) {
        System.out.println("ACCEPT " + event.getInvoiceId());
    }

    @ServiceActivator(inputChannel = "discardedInvoiceEvents")
    public void auditRejectedEvent(InvoicePaidEvent event) {
        System.out.println("DISCARD " + event.getInvoiceId());
    }
}
~~~

`@Filter` invokes the predicate method with the message payload. If it returns `true`, the message goes to `validInvoiceEvents`. If it returns `false`, the message goes to `discardedInvoiceEvents` because `discardChannel` is configured. Without a discard channel configured, rejected messages are normally dropped per the default filter policy; you can configure throwing an exception on rejection if business rules require it.

**Note:** this is **filtering after the event has entered the flow**. It inspects the `amount` property, which the `eventTypes` filter cannot do.

### 3.4. Publishing Events from the Service

`InvoicePaymentService.java`:

~~~java
package com.example.billing;

import java.math.BigDecimal;
import java.time.Instant;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class InvoicePaymentService {

    private final ApplicationEventPublisher publisher;

    public InvoicePaymentService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void announcePaid(String invoiceId, BigDecimal amount) {
        publisher.publishEvent(
                new InvoicePaidEvent(
                        this,
                        invoiceId,
                        amount,
                        Instant.now()));
    }
}
~~~

Sample calls:

~~~java
paymentService.announcePaid(
        "INV-1001", new BigDecimal("150.00"));

paymentService.announcePaid(
        "INV-1002", BigDecimal.ZERO);
~~~

Expected output with the default synchronous multicaster and `DirectChannel`s:

~~~text
ACCEPT INV-1001
DISCARD INV-1002
~~~

Wrong-type events such as `ContextRefreshedEvent` or `InvoiceCancelledEvent` do not appear in those two lines because they do not pass the inbound type filter.

The example above uses **one** inbound adapter for `rawInvoiceEvents`. If you add another adapter pointing to this same channel and listening to overlapping event types, you can generate two message deliveries from one event; therefore review the entire context topology when inspecting consumer invocation counts.

## 4. Why Not Filter Solely with @Filter?

You could let the inbound adapter accept all events and then use `@Filter` with an `instanceof` check. However, that turns a dedicated invoice flow into a receiver for many unrelated events, including Spring framework events. Consequences:

- Channels and filters must process unnecessary traffic.
- If the `@Filter` signature expects `InvoicePaidEvent` and another event enters, payload type conversion can fail before the predicate ever returns `false`.
- If the flow has multiple subscribers or a `WireTap`, unrelated events can be forwarded to other components before the business filter decides.
- When both inbound and outbound event adapters exist in the same application, broad acceptance increases the risk of re-emitting the same event in a loop.

Thus, **filtering by type at the ingestion boundary** and **filtering by attributes once inside the flow** cleanly separates responsibilities.

If a flow must accept multiple event types for different tasks, use separate dedicated inbound adapters/output channels or add a `Router` with a clear contract. Do not force every event into one payload type just to save channel beans.

## 5. Nature of Event Type, Payload, and Headers

An event can take different shapes across the Spring and Spring Integration boundary:

| Publishing style | Event type in Spring | Content once converted to message | Impact on filtering |
| --- | --- | --- | --- |
| `publishEvent(new InvoicePaidEvent(...))` | `InvoicePaidEvent` | Usually the `InvoicePaidEvent` object itself | Filtering by `InvoicePaidEvent.class` fits the main example |
| `publishEvent(new InvoicePaidPayload(...))` with a POJO/record | Spring wraps into `PayloadApplicationEvent<InvoicePaidPayload>` | Inbound event adapter can unwrap into `InvoicePaidPayload` | Check your version's payload/`PayloadApplicationEvent` matching rules; do not assume wrapper and POJO are the same class |
| Publishing `MessagingEvent` wrapping a `Message<?>` | `MessagingEvent` | Adapter can forward the original message with headers intact | Filtering by `MessagingEvent.class` admits multiple payload types, so a post-channel payload filter may be needed |
| Framework events like `ContextRefreshedEvent` | `ContextRefreshedEvent` | Framework event if adapter is configured to accept it | Should not enter business flows unless there is a specific use case |

Key point: the **event type before the inbound adapter** and the **payload type after the inbound adapter** can differ. For POJO events, Spring uses `PayloadApplicationEvent` to carry the payload; for `MessagingEvent`, Spring Integration can preserve the `Message<?>` (payload, headers, metadata).

### When the Source Emits a POJO

Define the business payload:

~~~java
public record InvoicePaidPayload(
        String invoiceId, BigDecimal amount) {
}
~~~

and publish:

~~~java
publisher.publishEvent(
        new InvoicePaidPayload("INV-2001", new BigDecimal("80.00")));
~~~

Spring Framework supports POJO events via `PayloadApplicationEvent`. Do not copy the `InvoicePaidEvent.class` example configuration and expect it to catch POJO events, since the Spring event and payload have different classes.

If you choose a POJO as the contract, verify `eventTypes` filtering behavior in your Spring Integration version and write tests confirming it. Another clean option is using a dedicated `ApplicationEvent` class for input, then converting it to a domain record in a `@Transformer` after the inbound adapter. This lets you restrict types at the adapter without wrapper ambiguity.

### When Headers Must Be Preserved

If an event comes from an outbound adapter with `publishPayload=false`, a POJO payload can be wrapped in `MessagingEvent`. The receiver can get the full message carrying headers like `correlationId` and `traceId`:

~~~java
import org.springframework.integration.event.core.MessagingEvent;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<InvoicePaidPayload> original = MessageBuilder
        .withPayload(new InvoicePaidPayload(
                "INV-2002", new BigDecimal("99.00")))
        .setHeader("correlationId", "corr-2002")
        .build();

publisher.publishEvent(new MessagingEvent(original));
~~~

If the inbound adapter accepts `MessagingEvent` and forwards the original message, a predicate after the channel should inspect the **payload type** and required headers; `setEventTypes(MessagingEvent.class)` alone does not distinguish `InvoicePaidPayload` from other payloads.

Conversely, if publishing a POJO directly or setting `publishPayload=true` on the outbound handler, `Message<?>` headers do not automatically become properties on the POJO event. To preserve traceability, include `correlationId` in the event contract or keep the message intact using an appropriate event wrapper.

## 6. Filtering Based on payloadExpression: Selecting Data Before Filtering

`ApplicationEventListeningMessageProducer` can use `payloadExpression` to extract data from an application event when building the message payload. For example, with `InvoicePaidEvent`, if downstream only needs the invoice ID, you can configure:

~~~java
import org.springframework.expression.spel.standard.SpelExpressionParser;

adapter.setPayloadExpression(
        new SpelExpressionParser().parseExpression("invoiceId"));
~~~

The output message payload from the inbound adapter is then a `String` such as `"INV-1001"` instead of an `InvoicePaidEvent` object. **Downstream `@Filter` and `@ServiceActivator` methods after the channel must update their signatures accordingly**.

You can combine:

1. `eventTypes`: excludes events other than `InvoicePaidEvent`.
2. `payloadExpression`: extracts `invoiceId` or the needed field from valid events.
3. `@Filter`: checks the value of the extracted payload.

However, extracting only `invoiceId` removes `amount` from the payload so predicates can no longer inspect it. Choose the mapping order or DTO design carefully to avoid discarding fields needed by business logic.

For special events like `MessagingEvent` whose source is a `Message<?>`, the inbound adapter follows the rule of preserving the original message; do not assume a payload expression applies identically to every event kind. Test actual mapping behavior before tying validation to an expression.

## 7. Configuring Event Filtering in XML

In a Spring Integration project using XML namespaces, you can restrict event types directly on the inbound adapter:

~~~xml
<int:channel id="rawInvoiceEvents"/>

<int-event:inbound-channel-adapter
    channel="rawInvoiceEvents"
    event-types="com.example.billing.InvoicePaidEvent"/>
~~~

This snippet sits inside an XML file declaring the `int` and `int-event` namespaces and matching schemas. The `event-types` attribute serves the same purpose as Java `setEventTypes(...)`.

If downstream still needs to check `amount > 0`, add a filter inside the flow; `event-types` only decides the **event type**. In applications using Java annotation config as in Section 3, the two styles are alternatives—do not declare duplicate adapters in both XML and Java for the same flow unless doubling execution is intentional.

## 8. When Rejecting an Event: Silence, Discard, or Error?

Not every situation should be treated as an error.

| Situation | Appropriate outcome | Reason |
| --- | --- | --- |
| Spring emits `ContextRefreshedEvent`, while flow only accepts `InvoicePaidEvent` | Inbound type filter ignores it | Out-of-contract event, not a business error |
| Right event type, `amount == 0`, rule says skip | `@Filter` rejects, sends to `discardChannel` if audit is needed | Rejected by business condition |
| Right event type, missing required field | Validation with clear error reporting | Likely a contract violation; silent discard hides the bug |
| Predicate throws an exception reading data | Endpoint exception / error flow mechanism | An exception is **not** a boolean `false` result |
| Downstream HTTP/Kafka/JMS fails after passing filter | Adapter/transport error handling and retries as required | Event filter is not responsible for delivery confirmation |

`discardChannel` receives **rejected messages**, which is convenient for auditing or metrics. If dropping messages altogether, maintain counters by event type or rejection reason under high traffic.

To throw an exception instead of the default discard when a condition fails, `@Filter` has `throwExceptionOnRejection`. Use it when a rejected event is considered a serious error that the publisher must know about, but trace the exception path before enabling it, especially in asynchronous setups.

## 9. Synchronicity, Async, and Error Channels

By default, Spring's `SimpleApplicationEventMulticaster` and Spring Integration's `DirectChannel` both operate synchronously. When a service calls `publisher.publishEvent(...)`, the adapter can immediately receive the event, push the message into the channel, and invoke `@Filter`/service activators on the **same thread**.

This means:

- A slow predicate or consumer slows down the publishing thread.
- An exception from a filter/handler can propagate back to the publisher, depending on error handler and endpoint configuration.
- If the event is published inside a transaction, synchronous filter execution can run **before commit**, even when the type matches.

When using `ExecutorChannel`, `@Async`, or a multicaster executor, the execution thread and error path change. A successful `send(...)` or returning `publishEvent(...)` no longer means all async consumers have finished.

For events that must be processed **only after transaction commit**, `eventTypes` cannot solve that requirement. Use `@TransactionalEventListener(phase = AFTER_COMMIT)` as a post-commit bridge, or design an outbox when guaranteed delivery to external systems is required. Switching to an executor before registering a transaction-bound listener can cause the thread-bound transaction context to be absent.

**Reliability note:** type filtering before the flow reduces load and prevents mismatched handling, yet Spring application events remain an in-process mechanism without built-in durable persistence, restarts across crashes, or dead-letter queues.

## 10. Preventing Loops Between Inbound and Outbound Event Adapters

When one application both receives and publishes Spring events, a loop can occur:

~~~mermaid
flowchart LR
    I["Inbound event adapter"] --> F["Integration flow"]
    F --> O["Outbound event publisher"]
    O -->|"Re-emits same event type"| I
~~~

For example, the inbound adapter listens for `InvoicePaidEvent.class`, the flow processes it, and the outbound handler publishes the exact same `InvoicePaidEvent` back into the Spring context. If the inbound adapter keeps listening to that event, each publication triggers another cycle.

Reduce risk by:

- Restricting inbound `eventTypes` to **only the flow's input event types**.
- Separating **input** and **output** events by type or contract structure when their business meanings differ.
- Emitting new events only after performing the required business state transition; never re-emit the received event by default.
- If logic genuinely must re-ingest the same type, enforce an explicit stopping condition or deduplication, such as tracking processed `eventId`s.
- Auditing the entire Spring context, since events can reach listeners outside the flow you just wrote.

**Do not rely solely on a type filter to prevent loops if outbound re-emits the exact type allowed by inbound.** In that case you must change the topology or design an explicit termination guard.

## 11. Testing Filters at the Right Boundaries

A solid test suite should observe **three separate points**: messages entering `rawInvoiceEvents`, messages reaching `validInvoiceEvents`, and messages routed to `discardedInvoiceEvents`.

| Test | Published event | After `eventTypes` | After `@Filter` |
| --- | --- | --- | --- |
| T1 | `InvoicePaidEvent("INV-01", 100.00)` | Message enters `rawInvoiceEvents` | Goes only to `validInvoiceEvents` |
| T2 | `InvoicePaidEvent("INV-02", 0.00)` | Message enters `rawInvoiceEvents` | Goes only to `discardedInvoiceEvents` |
| T3 | `InvoicePaidEvent("INV-03", -5.00)` | Message enters `rawInvoiceEvents` | Goes only to `discardedInvoiceEvents` |
| T4 | `ContextRefreshedEvent` | No message from `InvoicePaid`-specific adapter | No example consumer runs |
| T5 | `InvoiceCancelledEvent` | No message from `InvoicePaid`-specific adapter | No example consumer runs |
| T6 | `MessagingEvent` carrying `InvoicePaidPayload`, while inbound listens only to `InvoicePaidEvent.class` | No message from `InvoicePaid`-specific adapter | No example consumer runs |
| T7 | Update config to accept `MessagingEvent.class` | Message carries original payload/headers | Must update predicate/consumer to match the new payload type |

How to test:

1. In a Spring test context, replace example consumers with **probes** recording event IDs and channel names; use `CopyOnWriteArrayList` or thread-safe structures if an executor is involved.
2. Publish each event individually via `ApplicationEventPublisher`; reset probes after each case.
3. Assert the exact branch and invocation count rather than checking console logs.
4. With `DirectChannel` and a synchronous multicaster, results can be asserted right after `publishEvent(...)` returns.
5. When switching to async, use `CountDownLatch`/`Awaitility` with sensible timeouts instead of relying on `Thread.sleep(...)`.
6. Add a test for subclasses of the event type if the contract intends to accept subclasses, confirming filtering behavior on your exact version.

**Data-type failure experiment:** temporarily remove `setEventTypes(...)` while keeping the predicate expecting `InvoicePaidEvent`. Publish a framework event and observe where the failure occurs. Then restore the type filter and confirm the framework event never enters the flow. This experiment distinguishes "event blocked properly at entry" from "event entered the flow and failed during processing".

## 12. Design Checklist

Before deploying an event flow to production, answer clearly:

| Question | Decision to document in design |
| --- | --- |
| Which **event types** does the flow accept? | Explicit allowlist in `setEventTypes(...)` |
| Could framework or other-module events appear? | Restrict types and test out-of-contract events |
| After inbound, what is the **actual payload type**? | Contracts for `@Filter`, `@Transformer`, and service activators |
| Are `correlationId` and `traceId` headers needed? | Use an event DTO with metadata or an appropriate message wrapper |
| Which business conditions require further filtering? | Predicate after inbound, discard/metrics |
| Is rejecting an event an error? | Drop, discard channel, or throw exception |
| Could consumers run before commit? | Transaction-bound listener or outbox when needed |
| Could an inbound/outbound loop form? | Separate event types and stopping conditions |
| Does an external system require delivery guarantees? | Choose a dedicated outbound adapter and retry/durable transport |

## 13. Practical Exercises

**Exercise 1 — Accurate event type filtering.** Write three event classes: `InvoicePaidEvent`, `InvoiceCancelledEvent`, and `InventoryUpdatedEvent`. Configure inbound to accept only `InvoicePaidEvent` and verify the other two never appear on `rawInvoiceEvents`.

**Exercise 2 — Discard and audit.** Extend `InvoicePaidEvent` with `currency`. Accept only events where `amount > 0` and `currency == "VND"`, sending rejected messages to `discardedInvoiceEvents` to record the rejection reason.

**Exercise 3 — Payload mapping.** Configure `payloadExpression` to return `invoiceId`; update the transformer or consumer to accept `String`, then explain why the old `amount`-based filter can no longer be used unchanged.

**Exercise 4 — Preserving metadata.** Publish a `MessagingEvent` with a `correlationId` message header, configure the matching adapter, and verify the header survives across the event boundary. Contrast with publishing a POJO directly.

**Exercise 5 — Loop prevention.** Build a flow with both inbound and outbound event adapters. Demonstrate how a topology re-emitting the same event type risks looping, then fix it by separating the output event type or adding deduplication.

**Exercise 6 — Connecting external systems.** After the `validInvoiceEvents` branch, attach an appropriate outbound adapter to forward filtered invoice events to Kafka/JMS or HTTP. Distinguish contract errors, filter rejections, and external delivery failures; identify where retries and idempotency belong.

## References

- [Spring Integration — Spring ApplicationEvent Support](https://docs.spring.io/spring-integration/reference/event.html).
- [Spring Integration API — ApplicationEventListeningMessageProducer](https://docs.spring.io/spring-integration/api/org/springframework/integration/event/inbound/ApplicationEventListeningMessageProducer.html).
- [Spring Integration — Message Filter](https://docs.spring.io/spring-integration/reference/filter.html).
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html).
- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events).

# ApplicationEventPublishingMessageHandler: Emitting Messages to the Spring Event System

## Lesson Objectives

In the **Event Adapter** chapter of the **SPRING_INTEGRATION_ADAPTERS** module, `ApplicationEventPublishingMessageHandler` is the outbound adapter connecting a **Spring Integration** flow with the **Spring ApplicationEvent** mechanism. After this lesson, you will be able to:

- Explain the handler's role in the flow `MessageChannel → MessageHandler → ApplicationEventPublisher → listener`.
- Configure the handler in Java, distinguishing the default mode and `setPublishPayload(true)`.
- Decide when to preserve the full `Message<?>` and headers, and when to publish a pure domain event.
- Verify event publication, identify error boundaries, and avoid event loops.

This is an integration point **inside the Spring `ApplicationContext`**. Unlike outbound adapters going to HTTP, JMS, Kafka, SFTP, or external systems, this handler delivers Spring Integration data to components listening for events within the same application/Spring context. It is useful when an integration flow has processed, routed, or transformed a message and needs to notify other business components of the result.

## 1. How It Works

`ApplicationEventPublishingMessageHandler` resides in package `org.springframework.integration.event.outbound`, extends `AbstractMessageHandler`, and implements `ApplicationEventPublisherAware`. Spring injects `ApplicationEventPublisher` into the bean; whenever a message arrives at the endpoint wired to the handler, the handler invokes Spring's event publishing mechanism.

~~~mermaid
flowchart LR
    A["Inbound adapter / gateway / service"] --> B["MessageChannel"]
    B --> C["ApplicationEventPublishingMessageHandler"]
    C --> D["Spring ApplicationEventPublisher"]
    D --> E["@EventListener"]
    D --> F["ApplicationListener"]
~~~

For example, after an integration flow receives order data, validates it, and normalizes the payload, the handler emits an `OrderCreated` event so a notification component or audit recorder can process it. The component sending the message only needs to know the `MessageChannel`, without directly calling each listener.

**Data flow direction to remember:**

- **Outbound:** Spring Integration `Message<?>` → `ApplicationEventPublishingMessageHandler` → Spring event.
- **Inbound (reverse direction):** Spring event → `ApplicationEventListeningMessageProducer` → Spring Integration `Message<?>`. That is a different adapter; do not use `ApplicationEventPublishingMessageHandler` to receive events.

The handler has no request/reply contract: it publishes the event and completes message handling as an outbound endpoint. If a listener needs to return a value, design a separate flow to receive the result; do not expect the handler to produce a reply message automatically.

## 2. What Payload Is Actually Published?

The deciding rule is the `publishPayload` property. Its default value is `false`.

| Payload arriving at handler | `publishPayload` | Data Spring receives | Impact on listener |
| --- | --- | --- | --- |
| A domain object, e.g., `OrderCreated` | `false` (default) | `MessagingEvent` wrapping **the entire** `Message<?>` | Listen for `MessagingEvent`, extract `event.getMessage().getPayload()` and headers |
| A domain object, e.g., `OrderCreated` | `true` | The `OrderCreated` object itself passed to `publishEvent(Object)` | Can use `@EventListener` with parameter `OrderCreated`; original message headers do not accompany it automatically |
| Payload is already an `ApplicationEvent` | `false` or `true` | That `ApplicationEvent` object | Listener matching the published event type |

When `publishPayload=false` and the payload is not already an `ApplicationEvent`, `MessagingEvent` is `org.springframework.integration.event.core.MessagingEvent`, which provides `getMessage()` to retrieve the full message.

When `publishPayload=true` and the payload is a POJO/record, Spring Framework supports publishing that object via `ApplicationEventPublisher.publishEvent(Object)`. The framework may use `PayloadApplicationEvent` internally; an `@EventListener` method accepting the matching payload type still works. Distinguish Spring's internal wrapper from `MessagingEvent` created by Spring Integration in default mode.

Consider this example message:

~~~text
payload = OrderCreated(orderId="ORD-1042")
headers = { traceId="abc-123", ... }
~~~

- Default mode: a `MessagingEvent` listener can read both `OrderCreated` and `traceId` from the message.
- `true` mode: an `OrderCreated` listener receives the domain object; if `traceId` is needed, place it in the event or design an event contract containing the required metadata.

**Mode selection rule:** publish the payload directly if you want a clean business API and listeners independent of Spring Integration. Keep the default if recipients need metadata or headers from the original message.

## 3. Installing the Dependency

The Spring Integration event support module is `spring-integration-event`. In a Spring Boot application managing compatible dependency versions:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-integration")
    implementation("org.springframework.integration:spring-integration-event")
}
~~~

If not using Spring Boot dependency management, specify a `spring-integration-event` version compatible with the other Spring Integration modules in your project. The examples below use Java 17+ (records) and annotation configuration.

## 4. Complete Example: From MessageChannel to @EventListener

Suppose order creation has already occurred at the business layer. A service needs to send `OrderCreated` information into a Spring Integration channel; a Spring listener will perform secondary actions such as audit logging or sending notifications.

**Step 1 — Define the business event.**

`OrderCreated.java`:

~~~java
package com.example.orders;

import java.time.Instant;

public record OrderCreated(String orderId, Instant occurredAt) {
}
~~~

**Step 2 — Create the channel and attach the outbound handler.**

`OrderEventIntegrationConfig.java`:

~~~java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.event.outbound.ApplicationEventPublishingMessageHandler;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class OrderEventIntegrationConfig {

    @Bean
    public MessageChannel orderEventChannel() {
        return new DirectChannel();
    }

    @Bean
    @ServiceActivator(inputChannel = "orderEventChannel")
    public ApplicationEventPublishingMessageHandler orderEventPublisher() {
        var handler = new ApplicationEventPublishingMessageHandler();
        handler.setPublishPayload(true);
        return handler;
    }
}
~~~

`@ServiceActivator(inputChannel = "orderEventChannel")` registers the handler as a consumer of the channel. Setting `setPublishPayload(true)` here is intentional: the business listener will receive `OrderCreated`, not `MessagingEvent`.

**Step 3 — Send the message from the service.**

`OrderCommandService.java`:

~~~java
package com.example.orders;

import java.time.Instant;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderCommandService {

    private final MessageChannel orderEventChannel;

    public OrderCommandService(
            @Qualifier("orderEventChannel") MessageChannel orderEventChannel) {
        this.orderEventChannel = orderEventChannel;
    }

    public void notifyOrderCreated(String orderId, String traceId) {
        var payload = new OrderCreated(orderId, Instant.now());
        var message = MessageBuilder.withPayload(payload)
                .setHeader("traceId", traceId)
                .build();

        if (!orderEventChannel.send(message)) {
            throw new IllegalStateException("Cannot dispatch OrderCreated");
        }
    }
}
~~~

In a real system, call `notifyOrderCreated` at a point appropriate for your transaction boundary and business requirements. This example only illustrates sending a message into the adapter; it does not include persisting the order to a database.

**Step 4 — Consume the Spring event.**

`OrderCreatedListener.java`:

~~~java
package com.example.orders;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @EventListener
    public void onOrderCreated(OrderCreated event) {
        System.out.println("Handle order: " + event.orderId());
    }
}
~~~

When `notifyOrderCreated("ORD-1042", "abc-123")` is called, the processing sequence in the configuration above is:

1. The service builds `Message<OrderCreated>` and sends it to the `DirectChannel`.
2. `@ServiceActivator` passes the message to `ApplicationEventPublishingMessageHandler`.
3. The handler publishes the `OrderCreated` payload via `ApplicationEventPublisher`.
4. Spring invokes `onOrderCreated(OrderCreated)` in the default synchronous context; the listener receives `orderId = "ORD-1042"`.

If no matching listener exists, Spring can still accept the event without triggering any business action. Therefore, `send(...)` succeeding does not prove that a notification was sent or an audit record was saved.

## 5. When the Full Message and Headers Are Needed

Change the configuration in Step 2 by **removing** the `setPublishPayload(true)` call (or setting it to `false`). This is the handler's default mode:

~~~java
@Bean
@ServiceActivator(inputChannel = "orderEventChannel")
public ApplicationEventPublishingMessageHandler orderEventPublisher() {
    return new ApplicationEventPublishingMessageHandler();
}
~~~

Now the listener reads `MessagingEvent`:

~~~java
package com.example.orders;

import org.springframework.context.event.EventListener;
import org.springframework.integration.event.core.MessagingEvent;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class MessageAuditListener {

    @EventListener
    public void onMessage(MessagingEvent event) {
        Message<?> message = event.getMessage();
        Object payload = message.getPayload();
        Object traceId = message.getHeaders().get("traceId");

        if (payload instanceof OrderCreated order) {
            System.out.println(
                    "Audit " + order.orderId() + " (traceId=" + traceId + ")");
        }
    }
}
~~~

The two examples in Section 4 and Section 5 are **two alternative approaches**. When practicing, use the listener matching the current `publishPayload` setting. Do not register two outbound handlers simultaneously on the same `DirectChannel` expecting every message to automatically reach both: `DirectChannel` by default dispatches each message to one selected subscriber.

## 6. Configuration with Java DSL or XML

If the project uses Spring Integration Java DSL, you can create the same outbound endpoint without declaring `@ServiceActivator`:

~~~java
@Bean
public IntegrationFlow orderEventFlow() {
    var handler = new ApplicationEventPublishingMessageHandler();
    handler.setPublishPayload(true);

    return IntegrationFlow.from("orderEventChannel")
            .handle(handler)
            .get();
}
~~~

The DSL snippet assumes the `orderEventChannel` bean already exists as in Section 4. Choose **one** way to register the endpoint (DSL or `@ServiceActivator`) for the demonstration flow; declaring both on a single `DirectChannel` creates two competing consumers.

With traditional XML namespace configuration:

~~~xml
<int:channel id="orderEventChannel"/>

<int-event:outbound-channel-adapter
    channel="orderEventChannel"
    publish-payload="true"/>
~~~

This is the core element in an XML configuration declaring the `int` and `int-event` namespaces and corresponding schemas. If you switch the channel to a `QueueChannel` (pollable), the outbound endpoint must have a poller to retrieve messages; you can tune the rate using `fixed-rate`, `max-messages-per-poll`, and `task-executor`. With a regular `DirectChannel`, processing begins immediately when the message is sent.

## 7. Synchronicity, Transactions, and Error Handling

The characteristics below determine whether this adapter fits your operational requirements.

| Scenario | What happens | How to design |
| --- | --- | --- |
| `DirectChannel` and default synchronous Spring listeners | Handler and listeners run in the sender's call chain; runtime errors from a listener can propagate back to the sender | Establish an explicit error policy; do not assume emitting an event always succeeds |
| `ExecutorChannel`, async poller, or listener running via `@Async` | Processing can occur on another thread; completion timing and error paths change | Configure error handling appropriate for each async boundary; do not assume exceptions always return to the sending service |
| Listener actions must run only after DB commit | Publishing before commit can expose uncommitted state to listeners; synchronous listeners can also affect the transaction | Consider `@TransactionalEventListener(phase = AFTER_COMMIT)` when publishing occurs within an appropriate transaction |
| Application stops or process crashes | Spring `ApplicationContext` events are not a durable queue | If cross-process retries, durable storage, or inter-service delivery are needed, use an outbox/appropriate message broker |
| Configuring both inbound and outbound event adapters | If inbound picks up the event just emitted by outbound and feeds it back into the same flow, an infinite loop can form | Restrict `eventTypes`, separate channels/flows, or apply filter conditions |

With `@TransactionalEventListener`, the listener depends on an active transaction (unless an appropriate fallback mechanism is enabled). When switching threads, consider transaction context propagation and post-commit requirements; do not treat this annotation as a delivery guarantee mechanism.

**Distinguishing internal events from message brokers:** `ApplicationEventPublishingMessageHandler` does not automatically write events to Kafka/JMS/AMQP, nor does it add durable delivery guarantees, retries, dead-letter queues, or exactly-once semantics. It only uses the Spring `ApplicationContext` event publication mechanism. When cross-process communication is needed, choose the corresponding Spring Integration outbound adapter or gateway.

## 8. Testing and Diagnosis

To test the scenario in Section 4 in the sample application:

1. Start the Spring context containing `OrderEventIntegrationConfig` and `OrderCreatedListener`.
2. Call `orderCommandService.notifyOrderCreated("ORD-1042", "trace-01")`.
3. Verify the listener is invoked once with `OrderCreated.orderId() == "ORD-1042"`.
4. Switch the handler back to default and replace the listener with `MessageAuditListener` from Section 5; verify `traceId == "trace-01"` can be read from headers.
5. Have a listener throw an exception when using `DirectChannel` and synchronous listeners to observe the exception propagating back to the caller; repeat with an async channel to see the different error boundary.

In automated tests, use a test listener that records events into temporary storage such as `AtomicReference<OrderCreated>` or a synchronized list, then assert invocation counts and event contents. If you only see a `Message sent` log without the listener running, check in order:

- Is the handler registered on the right `inputChannel`, and is the bean inside the active Spring context?
- Does the listener expect `OrderCreated` or `MessagingEvent`? What is the current `publishPayload` setting?
- Is another consumer also listening on the `DirectChannel`? If you want to deliver to multiple Spring Integration handlers, consider `PublishSubscribeChannel`; if you want multiple Spring listeners to receive the same event, register multiple matching Spring listeners.
- Are type filtering, `@Async`, a poller, or a transaction listener altering when reception happens?
- Was an inbound event adapter accidentally wired back to a channel leading to the outbound handler, creating a loop?

## 9. Practical Exercises

**Exercise 1 — Domain Event:** Build a flow receiving `PaymentConfirmed(paymentId, orderId)`, publish the payload directly, and use two independent listeners: updating a report and sending a notification. Observe both Spring listeners being invoked from a single event publication.

**Exercise 2 — Trace Tracking:** Switch back to `publishPayload=false`, put `correlationId` in a message header, and create a `MessagingEvent` listener to log `correlationId`. Explain why the `PaymentConfirmed` listener from Exercise 1 must be updated when payload publishing mode is not used.

**Exercise 3 — Error Analysis:** Have a listener throw `IllegalStateException`, and compare the exception path when using `DirectChannel` versus an asynchronous processing configuration. Identify where recovery mechanisms should be placed, and describe why internal events should not be used as a reliable queue between services.

## References

- [Spring Integration Reference — Spring ApplicationEvent Support](https://docs.spring.io/spring-integration/reference/event.html)
- [ApplicationEventPublishingMessageHandler API](https://docs.spring.io/spring-integration/api/org/springframework/integration/event/outbound/ApplicationEventPublishingMessageHandler.html)
- [MessagingEvent API](https://docs.spring.io/spring-integration/docs/6.2.6/api/org/springframework/integration/event/core/MessagingEvent.html)

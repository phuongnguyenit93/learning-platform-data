# Preserving Payload, Headers, and Message Identity

**Chapter:** Bridge  
**Lesson:** Preserving Payload, Headers, and Message Identity  
**Scope:** `SPRING_INTEGRATION_PATTERN` — practicing Enterprise Integration Patterns (EIP) with Spring Integration to build loosely coupled, extensible message flows; connecting Bridge with Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, while testing real runtime behavior.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the role of a **Bridge**: connecting two message channels to forward a message without intentionally transforming its content.
2. Distinguish **payload**, **headers**, **message identity** in Spring Messaging, and business **event identity**.
3. Understand why a Bridge can preserve a message within a local flow yet **does not guarantee** that the entire journey across adapters, converters, brokers, and retries preserves the same Java object or message ID.
4. Write Java DSL using `.bridge()`, pass a `Message<?>` across two channels, and verify data/identity with tests.
5. Identify boundaries that alter messages: `Transformer`, `Header Enricher`, `ChannelInterceptor`, serialization, message store, broker adapters, and request–reply.
6. Design correlation, idempotency, tracing, error handling, and observability for safe forwarding when an application runs asynchronously or across multiple services.

## 2. Bridge in Enterprise Integration Patterns

A Bridge is an integration pattern that **connects two message channels**. It is useful when two flow segments have an organizational boundary or different message-consumption mechanics, yet **do not need** payload transformation like a Transformer, classification like a Router, or filtering like a Filter.

A Bridge has two core responsibilities:

- Receive a message from the upstream channel.
- Forward that message to the downstream channel according to the flow configuration.

~~~mermaid
flowchart LR
    P["Producer"] --> C1["ordersIn: DirectChannel"]
    C1 --> B["Bridge"]
    B --> C2["ordersOut: QueueChannel"]
    C2 --> Q["Poller / Consumer"]
    Q --> H["Service Activator"]
~~~

In Spring Integration, a Bridge can be declared in Java DSL via `.bridge()`. By the intent of the pattern, a Bridge **does not act as a Transformer, Filter, or Header Enricher**. Therefore, for a simple internal forwarding segment, we expect the message's payload and headers to pass through.

However, *content correctness*, *message identity*, *error destination*, and *crash recovery* are distinct properties. They must be specified and tested separately.

### When Should You Use a Bridge?

- Connecting a `DirectChannel` to a `QueueChannel` to decouple the producer from a background-processing poller.
- Connecting two flow segments that are organized separately without needing to modify the payload.
- Creating an observation point or a place to attach dispatch/monitoring policies between two channels.
- Bridging from a source already configured as a `PollableChannel` to another channel without writing a pass-through handler just to return the message.

When two endpoints can connect directly and no separate boundary is needed, a Bridge may be unnecessary. Adding a Bridge **does not by itself create data durability, increase throughput, or resolve errors**.

## 3. Structure of a Spring Message

Spring Messaging represents a message using the `Message<T>` interface, consisting of:

| Component | Role | Example |
|---|---|---|
| **Payload** | Application data being transferred | `OrderPlaced(eventId, orderId)` |
| **Headers** | Metadata describing the message and how to handle it | `eventId`, `correlationId`, `replyChannel`, `errorChannel` |
| **Message ID** | Technical identifier of a Spring message, typically in `MessageHeaders.ID` | UUID assigned when the message is created |
| **Timestamp** | Message/header creation time managed by Spring | `MessageHeaders.TIMESTAMP` |
| **Business event ID** | Business event identifier stable across redeliveries | `evt-00042` |
| **Correlation ID** | Groups messages sharing the same context/request/group | `order-123` or `batch-7` |

Example of creating a message:

~~~java
record OrderPlaced(String eventId, String orderId, long totalInCents) {}

OrderPlaced event = new OrderPlaced("evt-00042", "order-123", 249900);

Message<OrderPlaced> message = MessageBuilder
        .withPayload(event)
        .setHeader("eventId", event.eventId())
        .setHeader("correlationId", event.orderId())
        .setHeader("traceId", "trace-demo-01")
        .build();

System.out.println(message.getPayload());
System.out.println(message.getHeaders().getId());
System.out.println(message.getHeaders().get("eventId"));
~~~

**Note:** `MessageHeaders.ID` is a message identifier generated/managed by Spring; `eventId` is created by the business domain. The two IDs have different meanings, even when both coexist in the same `Message<?>`.

### 3.1 MessageHeaders and Immutability

`MessageHeaders` is designed with an interface that **disallows direct mutation** like an arbitrary `Map`. To change headers, you typically need to create or rebuild a message via `MessageBuilder`, a `Header Enricher`, or an equivalent mechanism.

That **does not mean the message is deep-copied**:

- The payload may be a mutable Java object. If multiple components hold references to it, mutations inside the payload can become visible elsewhere.
- A header value can also hold a mutable object.
- A Bridge forwarding a message is not responsible for freezing every object inside the payload/headers.

For important business data, use `record`s, immutable value objects, validated data, or convert to a stable representation at the integration boundary.

## 4. Three Levels of “Identity” That Are Often Confused

Within a flow, saying “the message is still the same message” can mean three different things:

| Identity Level | Question | How to Check | Should It Be Used for Deduplication? |
|---|---|---|---|
| **Java object identity** | Do two variables point to the exact same `Message` object? | `first == second` | No: meaningful only within the same JVM and implementation-dependent. |
| **Spring message ID** | Does `MessageHeaders.ID` keep the same value? | `first.getHeaders().getId().equals(second.getHeaders().getId())` | No: the ID can change when creating a new message or crossing a transport. |
| **Business event identity** | Do two deliveries belong to the same business event? | Compare producer-assigned `eventId` stored in payload/header | Yes: suitable as an idempotency key when designed to be stable. |

**Correlation ID** differs from the three levels above. It links messages belonging to the same request, batch, or group for an Aggregator. Multiple distinct messages can share the same `correlationId` while each has its own ID.

~~~mermaid
flowchart TD
    E["Business event: evt-00042"] --> M1["Spring Message A: UUID-a"]
    E --> M2["Spring Message B: UUID-b (republish / retry)"]
    M1 --> C["correlationId = order-123"]
    M2 --> C
    C --> G["Group by order"]
~~~

In this example, both A and B represent the same business event; having two different Spring message IDs **does not make them two valid distinct orders**.

## 5. What Is Preserved Across a Local Bridge?

For a standard Bridge within the same application, the goal is **forwarding the message**, so the following are expected not to be altered by the Bridge itself:

1. **Payload value** — type and data pass through without business transformation logic from the Bridge.
2. **Headers** — message metadata is forwarded, including custom headers; a Bridge should not be used as a header-sanitizing or header-rewriting step.
3. **Message identity** — when the same `Message<?>` is forwarded directly, the message ID is preserved. This behavior should be verified with tests for your actual configuration.

What **should not be inferred** from the points above:

- That a Bridge guarantees preserving the same **Java object reference** across all channel types and all serialization mechanisms.
- That every header will survive crossing HTTP, JMS, AMQP, or Kafka adapters.
- That a Bridge provides ACK, transactions, persistence, retries, and DLQ on its own.
- That a message retaining its ID means business logic processed it exactly once.
- That successful forwarding by a Bridge means the downstream consumer has committed business state.

A `ChannelInterceptor` can replace a message in `preSend`; a `Transformer` after the Bridge can create a different message; a persistent store/adapter can serialize and reconstruct objects. Therefore, when stating that identity is preserved, state **the observed scope and the components along the path**.

### 5.1 Illustrating Two Boundaries

~~~mermaid
flowchart LR
    A["Message A: payload + headers + UUID-a"] --> B["Local Bridge"]
    B --> C["Message A: forwarded data"]
    C --> D["Outbound adapter + converter"]
    D --> E[("Broker")]
    E --> F["Inbound adapter"]
    F --> G["Message B: verify header mapping and UUID"]
~~~

On the left, no business transformation is intentionally performed by the Bridge. On the right, the client/protocol/adapter can convert the message to wire format and construct a new Spring message. To ensure correlation on both sides, use `eventId`/`correlationId` with explicit mapping.

## 6. Java DSL: Creating a Bridge from DirectChannel to QueueChannel

This example connects a synchronous channel into a queue for a consumer to read later. The queue is **local in-memory only**, used to verify forwarding, not to guarantee zero message loss on application restart.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class OrderBridgeConfig {

    @Bean
    MessageChannel ordersIn() {
        return new DirectChannel();
    }

    @Bean
    PollableChannel ordersOut() {
        return new QueueChannel(100);
    }

    @Bean
    IntegrationFlow orderBridgeFlow() {
        return IntegrationFlow
                .from("ordersIn")
                .bridge()
                .channel("ordersOut")
                .get();
    }
}
~~~

Explanation:

- `ordersIn` is the entry point for sending messages into the flow, using a `DirectChannel` to invoke handlers synchronously.
- `.bridge()` declares the message-forwarding endpoint.
- `ordersOut` is a `QueueChannel`, allowing a consumer to call `receive(timeout)` to retrieve messages.
- `100` is the internal queue capacity. When full, the producer may block or fail to send depending on the `send` call and timeout; test load limits accordingly.
- If no consumer is present yet, messages can wait in the queue; however, an in-memory queue does not preserve data after process termination.

The Bridge is placed to clarify the boundary. It does not turn `ordersOut` into a RabbitMQ queue, does not add a persistent message store by itself, and does not automatically catch exceptions from downstream handlers.

### 6.1 Sending a Message with Metadata

~~~java
OrderPlaced event = new OrderPlaced("evt-00042", "order-123", 249900);

Message<OrderPlaced> sent = MessageBuilder
        .withPayload(event)
        .setHeader("eventId", event.eventId())
        .setHeader("correlationId", event.orderId())
        .setHeader("sourceSystem", "checkout")
        .build();

boolean accepted = ordersIn.send(sent);
if (!accepted) {
    throw new IllegalStateException("Bridge input rejected message");
}
~~~

`send()` succeeding indicates the channel accepted the message under its contract. When `ordersOut` is an in-memory queue, `accepted == true` is **not** confirmation that the message was durably persisted or that the consumer finished processing.

### 6.2 Reading the Message from the Target Channel

~~~java
Message<?> received = ordersOut.receive(2_000);
if (received == null) {
    throw new IllegalStateException("No bridged message received");
}

System.out.println(received.getPayload());
System.out.println(received.getHeaders().get("eventId"));
System.out.println(received.getHeaders().getId());
~~~

The snippet assumes the calling code holds references to both beans `ordersIn` and `ordersOut`. In real implementations, inject them with `@Qualifier` or create sender/receiver services.

## 7. Automated Testing of Payload, Headers, and ID

Instead of only checking `send() == true`, receive the message at the other end and assert the specific fields. The test below uses Spring Test and JUnit 5; keep `OrderBridgeConfig` from the previous section on the same test classpath.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(OrderBridgeConfig.class)
class OrderBridgeTest {

    @Autowired
    @Qualifier("ordersIn")
    MessageChannel input;

    @Autowired
    @Qualifier("ordersOut")
    PollableChannel output;

    record OrderPlaced(String eventId, String orderId, long totalInCents) {}

    @Test
    void bridgeForwardsPayloadHeadersAndId() {
        OrderPlaced event =
                new OrderPlaced("evt-00042", "order-123", 249900);

        Message<OrderPlaced> sent = MessageBuilder
                .withPayload(event)
                .setHeader("eventId", event.eventId())
                .setHeader("correlationId", event.orderId())
                .setHeader("sourceSystem", "checkout")
                .build();

        assertTrue(input.send(sent));

        Message<?> received = output.receive(2_000);
        assertNotNull(received);

        // No Transformer along the path.
        assertEquals(sent.getPayload(), received.getPayload());

        // Required headers are preserved.
        assertEquals("evt-00042", received.getHeaders().get("eventId"));
        assertEquals("order-123", received.getHeaders().get("correlationId"));
        assertEquals("checkout", received.getHeaders().get("sourceSystem"));

        // Expected for this specific local-forwarding Bridge configuration.
        assertEquals(sent.getHeaders().getId(),
                     received.getHeaders().getId());
    }
}
~~~

**Scope of assertion:** the test verifies an internal Bridge connecting a `DirectChannel` to a `QueueChannel` with no converter/interceptor modifying the message. This test result is **not** proof that the ID will remain unchanged across Kafka/JMS/AMQP, HTTP, serializers, retries, or all framework versions.

If you need to verify **the same object reference**, you can add `assertSame(sent, received)` for a specific configuration; that is an expectation about the current execution path/implementation and should be kept separate from testing the contract of **preserving payload value, headers, and ID**. Durable or distributed integrations cannot use `==` as a correctness criterion.

## 8. Do All Channels “Forward the Same Way”?

A Bridge is a forwarding handler, but **the channels before and after the Bridge determine scheduling and execution semantics**.

| Boundary | Primary Behavior | What to Verify |
|---|---|---|
| `DirectChannel` → Bridge → `DirectChannel` | Synchronous handler, typically on the calling thread. | Blocking time, exception propagation, current transaction. |
| `DirectChannel` → Bridge → `QueueChannel` | Enqueues for a consumer to read later. | Capacity, wait time, persistence across restart, consuming thread. |
| `QueueChannel` → Bridge → another channel | Pollable source requires a poller to pull data. | Poller, dequeue transaction, retry on handler failure. |
| `ExecutorChannel` → Bridge → another channel | Dispatches work asynchronously via an executor. | Rejection, executor bounds, error handling on another thread. |
| `PublishSubscribeChannel` → Bridge → target | Multiple subscribers or branches depending on configuration. | What each subscriber receives, exception handling, and ordering. |
| Bridge → outbound adapter | Crosses from an internal channel to an external system. | Converter, header mapping, publisher confirms, ACK, or offset. |

### 8.1 Configuring a Bridge from a QueueChannel with a Poller

If the input is a `PollableChannel`, the flow needs to be triggered by a poller. Illustrative example in a **separate** configuration from `OrderBridgeConfig` above:

~~~java
@Bean
IntegrationFlow bufferedBridgeFlow() {
    return IntegrationFlow
            .from("bufferedInput", endpoint -> endpoint.poller(
                    Pollers.fixedDelay(500).maxMessagesPerPoll(10)))
            .bridge()
            .channel("nextChannel")
            .get();
}
~~~

This assumes `bufferedInput` of type `PollableChannel` and an appropriate `nextChannel` bean are already declared. Do not declare two flows competing for the same input unless competing consumers are intentionally designed.

When a poller pulls a message and downstream fails, whether it **returns to the queue** depends on the message store, transaction, and error handler. A Bridge does not put messages back at the head of the queue on its own.

## 9. When Are Headers Altered or Lost?

A Bridge does not intentionally alter headers, but integration flows often have multiple components before or after it.

| Component/Step | Risk to Headers | Mitigation |
|---|---|---|
| `MessageBuilder` or `Transformer` creating a new message | Headers not copied, ID may become new. | Specify the list of headers to preserve; write targeted tests. |
| `Header Enricher` | Adds or overwrites metadata per configuration. | Distinguish business headers from framework-managed headers. |
| `ChannelInterceptor` | `preSend` may return a different message or reject sending. | Review interceptor configuration and test at both ends. |
| `Filter` or `Router` | Message may be dropped or sent to a different branch. | Separate drop/routing issues from message-mutation behavior. |
| `Splitter` | Splits one original message into child messages, creating sequence/correlation metadata. | Keep business `eventId` and add child identifiers when needed. |
| `Aggregator` | Combines multiple messages into one result message. | Define the resulting message ID and correlation semantics. |
| Serialization/persistent store | Objects may be reconstructed; class/serializer affects metadata. | Test deserialization, schema/version compatibility, and required headers. |
| AMQP/JMS/Kafka/HTTP adapter | Unsupported headers or headers mapped/dropped. | Declare a header mapper and integration-test over the real transport. |

Example of a Transformer building a new message while forgetting to carry over `eventId`:

~~~java
.handle(OrderPlaced.class, (order, headers) -> {
    // Incorrect propagation example if downstream needs eventId:
    return MessageBuilder.withPayload(order.orderId()).build();
})
~~~

The handler builds a **new message**, so you cannot assume custom headers from the original message will appear on the output. In Spring Integration, endpoints can apply header propagation/merge rules depending on handler type, so inspect the **actual output message** rather than guessing from a single `MessageBuilder` line inside a handler.

If you want to change the payload while keeping the necessary business headers, use a Transformer with explicit propagation rules and write a test:

~~~java
Message<String> transformed = MessageBuilder
        .withPayload(order.orderId())
        .copyHeaders(originalMessage.getHeaders())
        .setHeader("transformation", "order-to-id")
        .build();

// Payload changed; verify eventId/correlationId that must be kept.
// Technical ID/timestamp may be generated or handled per
// MessageBuilder/MessageHeaders policy: test specifically.
~~~

**Remember:** even when `copyHeaders(...)` is used, verify how **framework headers with special rules** such as ID and timestamp are handled. What should remain stable across systems are `eventId`, `correlationId`, and clearly defined business metadata.

## 10. Broker/Adapter Boundary: Message Identity Is Not Wire Identity

Suppose the flow runs as follows:

~~~mermaid
flowchart LR
    A["Message A in service X"] --> B["Bridge"]
    B --> C["AMQP / JMS / Kafka outbound adapter"]
    C --> D[("Broker")]
    D --> E["Inbound adapter"]
    E --> F["Message B in service Y"]
~~~

A broker typically does not store a raw Java `Message<?>` with its object reference. The adapter uses a converter, serializer, or header mapper to turn it into a transmittable wire format. On the receiving end, a different Spring `Message<?>` may be constructed.

Therefore, distinguish:

- **Payload equality:** after conversion via JSON/Avro/byte array, representation or data types may differ; compare business meaning after deserialization.
- **Header propagation:** custom headers may be unsupported or require mapper configuration; some headers are local-only, such as `replyChannel`/`errorChannel` objects, which are unsuitable as arbitrary wire data.
- **Spring message ID:** should not be treated as immutable across transports. A broker message ID may differ from the Spring message ID.
- **Business event ID:** include it in the payload schema or an explicitly mapped header and use it on the receiving side to deduplicate.
- **Trace/correlation:** preserve using a header format supported by both ends and test end-to-end.

When using Kafka, the offset identifies a **record's position within a partition**; it does not replace `eventId`. With RabbitMQ or JMS, consumer acknowledgments reflect transport delivery/transaction acknowledgment rules and do not turn `MessageHeaders.ID` into a business key.

## 11. Correlation, Aggregator, and Request–Reply

A Bridge is often inserted into flows with `Splitter`/`Aggregator` or a `Messaging Gateway`. Therefore, examine the metadata these components use.

### 11.1 Correlation Is Not Identity

In a flow splitting an order into three parts:

~~~text
OrderPlaced(eventId=evt-42, orderId=order-7)
    -> Splitter
       -> ReserveStock(part=1, correlationId=order-7)
       -> ChargePayment(part=2, correlationId=order-7)
       -> CreateInvoice(part=3, correlationId=order-7)
    -> Aggregator(correlationId=order-7)
~~~

The three child messages have **distinct message identifiers**, share `correlationId` for grouping, and can use `eventId`/child IDs for deduplication. A Bridge placed between channels does not configure the Aggregator's correlation strategy, release strategy, sequence size, or timeout.

If the Aggregator must recover across restarts, consider a persistent `MessageGroupStore` and handling redelivered child messages; **a Bridge does not store group state**.

### 11.2 Reply Channel and Error Channel

A Gateway or handler can use `replyChannel` and `errorChannel` to return results or error details within the application. A local Bridge can forward these headers when forwarding a message, but:

- A `replyChannel` pointing to an internal `MessageChannel` may cease to be meaningful once the message leaves the process.
- Replies must reach the place awaited by the consumer/gateway; timeouts and late replies must be handled.
- An error channel does not by itself guarantee retries, rollback, or NACK.
- When request–reply across a broker is needed, use a reply destination and correlation ID with an explicit contract.

Do not treat a Bridge as a **Gateway**; a Bridge forwards messages inside a flow, whereas a Gateway provides the calling interface and request–reply mapping mechanism for application code.

## 12. Identity Under Retry and Redelivery

Even if a Bridge preserves all information on the first pass, the system can still encounter duplicate messages due to consumer crashes, timeouts, or producer republishing.

For example:

1. Service A sends `OrderPlaced(eventId=evt-42)`.
2. The Bridge forwards the message to an outbound adapter and through a broker.
3. Service B commits the invoice in its database.
4. Service B crashes before the broker records the ACK/offset commit.
5. The message is redelivered; Service B sees `eventId=evt-42` again.

In this situation, whether the **Spring message ID is preserved or changes** matters far less than recognizing the same `eventId`. The consumer needs an idempotent operation, such as a unique key on `processed_event(event_id)` committed in the **same transaction** as the invoice change.

~~~sql
-- PostgreSQL illustration: perform the business write only if the event is not yet present.
BEGIN;

INSERT INTO processed_event(event_id)
VALUES (:eventId)
ON CONFLICT (event_id) DO NOTHING;

-- Application checks the insert count.
-- If 1: create/update the invoice in the same transaction.
-- If 0: this event was already processed; skip duplicate side effects.

COMMIT;
~~~

Avoid changing `eventId` on each retry; it must be a **stable key across deliveries of the same event**. For out-of-transaction side effects such as email or payment HTTP calls, use an idempotency key on the target system or a recoverable outbox.

## 13. Error Channel and Retries When a Bridge Encounters Errors

A Bridge does not execute business logic, yet sending to the target channel can still fail:

- `QueueChannel` is full or enqueue times out.
- `ExecutorChannel` rejects the task because the executor is overloaded.
- A downstream subscriber or synchronous handler throws a `MessagingException`.
- A poller reads a message from a persistent-store-backed queue, and the transaction/DB fails.
- The target channel has no suitable subscriber or is misconfigured.

How the system reacts depends on the thread and dispatch mechanism:

| Case | Typical Error Path | Meaning |
|---|---|---|
| Synchronous Bridge over `DirectChannel` | Exception can propagate to the `send()` caller. | Caller decides retry/rollback; no `ErrorMessage` is created automatically. |
| Poller-driven Bridge | Poller or configured error handler catches the exception. | Must verify dequeue rollback and message state. |
| Bridge to an async executor | Errors on the worker thread can route through the async boundary's error handler/error channel. | Producer may already have returned before the consumer fails. |
| Bridge to a durable channel | Writing the message can participate in an appropriate store transaction. | Durable storage is only guaranteed once the transaction commits. |

~~~mermaid
flowchart TD
    I["Message enters Bridge"] --> S{"Send to target channel"}
    S -->|Accepted| N["Proceed to next processing step"]
    S -->|Rejected / exception| E["Caller, poller, or async error handler"]
    E --> P{"Handling policy"}
    P -->|Retryable| R["Bounded retry + backoff"]
    P -->|Unrecoverable| Q["Appropriate quarantine / DLQ"]
    P -->|Transactional| T["Rollback when configured"]
    R --> S
~~~

The diagram shows **options that must be configured**, not behavior a Bridge performs automatically by default. Do not use `errorChannel` as proof that a message was persisted, ACKed, or will be redelivered.

## 14. Testing for Unintended Changes

A useful test suite covers both **message values** and **error handling**.

| Scenario | How to Reproduce | What to Assert |
|---|---|---|
| Plain forwarding | `DirectChannel → Bridge → QueueChannel` | Payload, custom headers, and message ID match expectations in the local setup. |
| Mutable object payload | Send a `Map` or mutable DTO and mutate a field. | Clarify whether references are shared; consider immutable payloads. |
| Header interceptor | Attach an interceptor capable of returning a different message. | Required headers remain; if ID changes, distinguish technical message ID vs. event ID. |
| Transformer after Bridge | Convert payload into a new DTO. | `eventId` and `correlationId` are copied per contract. |
| Splitter/Aggregator | Split into multiple parts sharing correlation. | Each part has proper ID/items; Aggregator does not hang on retry. |
| Broker adapter | Send via real AMQP/JMS/Kafka. | Metadata maps properly, payload deserializes, event ID stays stable. |
| Duplicate consumer delivery | Resend the same business event. | Only one business effect is committed. |
| Full queue | Reach `QueueChannel` capacity. | Send fails/times out explicitly; messages are not silently dropped. |
| Mid-processing restart | Stop the app after enqueue or after business commit. | Persistence and redelivery match configuration; no duplicate effects. |
| Handler failure | Throw an exception in the consumer after the Bridge. | Error path, transaction, and retry are verified, not inferred from `send()` alone. |

Add assertions on the final database state or side effects. Two messages carrying the same `eventId` arriving at a consumer can be normal under at-least-once delivery; business state is the true verification of duplicate protection.

### Diagnostic Checklist When Debugging

When receiving a message at the terminal end, inspect separately:

~~~text
businessEventId = payload.eventId / header.eventId
correlationId   = header.correlationId
springMessageId = headers.id
payloadType     = type(payload)
inputChannel    = ordersIn
outputChannel   = ordersOut
transport       = in-memory | JDBC store | AMQP | JMS | Kafka
deliveryAttempt = count (if provided by source/adapter)
traceId         = propagated trace context
~~~

Values for `deliveryAttempt` and `traceId` must come from actual metadata or be explicitly created by the application; do not assume every channel includes these two headers automatically.

## 15. Design Checklist for a Bridge Preserving Data and Identity

- [ ] Bridge is used to connect channels; it is not expected to act as a Transformer or Header Enricher.
- [ ] Exactly defined the scope in which **payload value**, **custom headers**, **Spring message ID**, **event ID**, and **correlation ID** must be preserved.
- [ ] Critical payloads/headers use immutable types or explicit copying rules; no reliance on implicit deep copying.
- [ ] Tests compare messages before and after the Bridge for the actual local setup, including ID and required headers.
- [ ] Header mapping/serialization is tested separately at every outbound/inbound adapter boundary.
- [ ] Neither `MessageHeaders.ID` nor Java reference `==` is used as a cross-service idempotency key.
- [ ] `eventId` stays stable across republishes, retries, and redeliveries; consumers are idempotent.
- [ ] Correlation/reply/error headers are controlled when using Splitter, Aggregator, Gateway, and brokers.
- [ ] Capacity limits, pollers, transactions, retry/backoff, and error handling are defined for input/output channels.
- [ ] Send failures, full queues, handler exceptions, restarts, and broker redeliveries are tested rather than checking only `send()`.
- [ ] Logs and tracing separate Spring message ID from business ID; backlog, retries, and errors on the bridge path are instrumented.

## 16. Conclusion

A Bridge is a **forwarding** component between channels in Spring Integration. On a simple local path, a Bridge is used to preserve payload and headers, and it can preserve the Spring message ID because it continues passing the same message along. Even so, **same Java object**, **same Spring message ID**, **same business event**, and **same correlation group** are four distinct concepts.

To build reliable EIP flows, inspect messages at real boundaries, keep `eventId` stable, implement correlation/idempotency in the right places, and explicitly design transactions, retries, error channels, and broker ACKs or offset commits. A Bridge connects flow segments without adding a transformation step; transport and recovery guarantees remain the responsibility of the surrounding channels, adapters, and processing infrastructure.

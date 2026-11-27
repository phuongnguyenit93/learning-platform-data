# Distinguishing Business Data from the Message Envelope

In **Spring Integration**, a processing flow does not simply pass a domain object from one step to the next. Each step typically works with a **message** composed of two parts: the **payload** (the content being processed) and **headers** (accompanying metadata so the system can route, correlate, and orchestrate processing). Distinguishing these two parts is fundamental to applying **Enterprise Integration Patterns** such as Router, Filter, Transformer, Splitter, Aggregator, and Gateway without coupling business logic too tightly to the messaging infrastructure.

After this lesson, you will be able to:

- Determine which information belongs in **business data** and which belongs in the **message envelope**.
- Read and construct `Message<T>` in the Spring Messaging/Spring Integration ecosystem.
- Choose the right place for identifiers, event timestamps, correlation info, retries, and error channels.
- Recognize common design mistakes when messages cross multiple endpoints or system boundaries.

## 1. Two Layers of Information in a Message

### Business Data: *What* Is the System Saying?

Business data describes the event, command, or state the application needs to process, such as:

- `orderId`: the order identifier.
- `customerId`: the customer placing the order.
- `totalAmount`: the total amount to be paid.
- `occurredAt`: the business timestamp when the order was recorded as created.

These fields must remain meaningful to the business even without Spring Integration, a message broker, or a specific processing flow. They normally reside in the **payload**, represented by an explicit type such as `OrderPlaced`, `PaymentRequested`, or `InventoryReserved`.

### Message Envelope: *How* Should the System Transport and Process It?

The message envelope is the wrapper around the payload that carries information for message exchange. In Spring's programming model, `org.springframework.messaging.Message<T>` has two main parts:

| Component | Type/Concept | Role |
| --- | --- | --- |
| `payload` | `T` | The data the endpoint will process; can be a Java object, string, byte array, or another type. |
| `headers` | `MessageHeaders` | Key–value metadata about the message and the integration process. |

Example of a message carrying an order-processing request:

```text
Message<OrderPlaced>
├── payload: OrderPlaced
│   ├── orderId       = "ORD-1001"
│   ├── customerId    = "CUS-08"
│   ├── totalAmount   = 350000
│   └── occurredAt    = 2026-11-21T02:00:00Z
└── headers: MessageHeaders
    ├── id            = message UUID
    ├── timestamp     = message creation time (if present)
    ├── traceId       = "trace-abc" (custom header)
    └── replyChannel  = reply channel (if required by the flow)
```

`orderId` **is not synonymous with** `headers.id`: a single order may be transmitted via many different messages. Likewise, `occurredAt` is the **business event** timestamp, which is not automatically equal to `headers.timestamp`, the time the **message** was created. A message can be reconstructed, resent, or transformed after the event occurred.

> **Foundational rule:** Do not use delivery metadata from a single message transmission as the canonical source of business truth that must be stored and queried long term.

## 2. Classification Table of Common Information

| Information | Typically Appropriate Location | Reason |
| --- | --- | --- |
| Order ID, amount, line items | Payload | Content that determines the outcome of business processing. |
| Time the order was placed | Payload/durable event contract | Must remain meaningful when stored, replayed, or audited. |
| Spring's `headers.id` | Message headers | Identifies a message at the framework layer; does not replace business keys. |
| `traceId` / `spanId` | Headers/observability metadata | Correlates logs and traces across steps; requires explicit mapping across adapters. |
| `replyChannel`, `errorChannel` | Headers | Coordinates replies and error handling within the flow. |
| `correlationId` for aggregating fragments from a Splitter | Headers | Tells the Aggregator which messages belong to the same processing group. |
| `sequenceNumber`, `sequenceSize` when a Splitter splits | Headers | Helps determine element position and group size. |
| Redelivery count or delivery info | Integration metadata, if provided by adapter/framework | Represents a delivery attempt; not guaranteed to exist on every transport. |
| `eventId` for deduplication after storage/replay | Durable event contract, which may be in the payload or a serialized event envelope | The identity of the **event** must outlive `MessageHeaders.id`. |

These are **design principles**, not a mandate that every system put the same field name in the same spot. For instance, `tenantId` may be a required business field in an event contract or merely internal routing metadata. The choice depends on whether the receiver needs that value to interpret the data properly and whether it must be retained during event replay.

### Three Envelope Layers That Are Easily Confused

1. **Spring message envelope:** the `Message<T>` object containing `payload` and `headers` inside the application.
2. **Contract-level event envelope:** e.g., JSON `{ "eventId": "...", "occurredAt": "...", "data": { ... } }`; this is part of the content **transmitted and persisted durably** according to a schema agreed upon by systems. This event envelope can very well be the payload of a Spring message.
3. **Transport envelope:** information used by Kafka, AMQP, or HTTP to transport data, such as topic, partition, routing key, or HTTP headers. Adapters may map some of this into Spring headers, but that does not mean they are the same structure.

Therefore, the question "put it in headers or payload?" must be answered with reference to **which boundary**: inside an `IntegrationFlow`, when publishing to a broker, or when defining a data contract between two systems.

## 3. Creating and Reading Messages with Spring

The example below uses Java 17+ to model a business event with a `record` and wrap it in a `Message<OrderPlaced>`:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

record OrderPlaced(
        String orderId,
        String customerId,
        BigDecimal totalAmount,
        Instant occurredAt
) {}

class MessageExample {
    void demonstrate() {
        OrderPlaced event = new OrderPlaced(
                "ORD-1001",
                "CUS-08",
                new BigDecimal("350000"),
                Instant.parse("2026-11-21T02:00:00Z")
        );

        Message<OrderPlaced> message = MessageBuilder.withPayload(event)
                .setHeader("traceId", "trace-abc")
                .setHeader("sourceSystem", "checkout")
                .build();

        // Read business facts from the payload.
        String orderId = message.getPayload().orderId();
        BigDecimal amount = message.getPayload().totalAmount();

        // Read processing metadata from headers.
        String traceId = (String) message.getHeaders().get("traceId");
        UUID messageId = message.getHeaders().getId();

        // orderId and messageId have different meanings.
        System.out.println(orderId + " / " + amount + " / " + traceId + " / " + messageId);
    }
}
```

Here `OrderPlaced` does not need to know whether the message is sent over a `DirectChannel`, RabbitMQ, or Kafka. The business problem is not forced to depend on channels, routing, or correlation concepts.

`MessageHeaders` is designed as a metadata map that is **not mutated directly** after message creation. When adding a header in a processing step, create a new message instead of trying to modify `message.getHeaders()`:

```java
Message<OrderPlaced> enriched = MessageBuilder.fromMessage(message)
        .setHeader("validationStage", "accepted")
        .build();
```

Do not assume every header, including `id` or `timestamp`, remains unchanged across every message reconstruction, transformer, or adapter. When identity must remain stable across multiple transmissions, manage a **durable event identifier** explicitly.

## 4. Significance of This Distinction in Enterprise Integration Patterns

Consider a flow that receives an order, checks processing conditions, splits each line item, and waits to aggregate results:

```mermaid
flowchart LR
    A[Gateway receives request] --> B[Channel]
    B --> C[Filter validates payload]
    C --> D[Router selects branch]
    D --> E[Transformer converts structure]
    E --> F[Splitter splits line items]
    F --> G[Service Activator processes each line]
    G --> H[Aggregator combines by correlation]
    H --> I[Reply or emit event]
```

**Gateway and Channel.** The gateway turns a call or input data into a message entering the flow, while the channel is the path between endpoints. The payload carries the business request; headers like `replyChannel`/`errorChannel` can help deliver replies or errors to the right place.

**Filter.** A filter usually decides whether to pass or drop based on the payload—for example, total amount must be greater than 0. A missing `traceId` should not turn a valid order into a business-invalid order unless an explicit operational requirement dictates it.

**Router.** A router picks a branch based on request type, business region, or order status. A technical router may also inspect routing headers. You should not treat a routing key as a canonical business field just because it appears on the message.

**Transformer.** A transformer changes the payload representation, such as turning an event into a processing command or normalizing a data structure. The returned message may still retain some input headers, but how headers are forwarded depends on the endpoint, configuration, and adapter; verify this whenever system boundaries change.

**Splitter and Aggregator.** A splitter can create child messages from an order, each carrying one line item's payload. Spring Integration provides mechanisms to attach metadata such as `correlationId`, `sequenceNumber`, and `sequenceSize` so the Aggregator recognizes messages belonging to the same group, depending on configuration. The `correlationId` used to **combine fragments of a single execution** is not necessarily `orderId`: an order may be reprocessed across multiple attempts, and sharing `orderId` as the group key can lead to mis-grouping.

**Retry and Error Channel.** Retry is a mechanism for handling transient failures; errors can be routed as error messages or via `errorChannel` depending on the flow. Retry metadata and exception details are not reliable business state data without a dedicated contract. If states like "paid" or "cancelled" must be recorded, update the business state in an appropriate persistent store; do not just set a header and treat the transaction as complete.

### Example Endpoint Reading Both Layers Properly

```java
import org.springframework.messaging.Message;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
class OrderReceiver {
    @ServiceActivator(inputChannel = "ordersIn")
    public void accept(Message<OrderPlaced> message) {
        OrderPlaced order = message.getPayload();
        String traceId = (String) message.getHeaders().get("traceId");

        // Business logic uses order.orderId(), order.totalAmount(), ...
        // Logging/observability can include traceId if present.
        // Persistence and idempotency checks must rely on durable keys.
    }
}
```

The snippet only demonstrates receiving a message in a **Service Activator**. To run as a complete application, you need to configure the `ordersIn` channel, the relevant Spring Integration dependencies, and the actual processing service. An endpoint can also accept only the payload object directly when it does not need access to headers.

## 5. When Messages Cross System Boundaries

Suppose the ordering system emits an event to the warehouse system. The warehouse side needs `orderId`, the line items, and a stable `eventId` to avoid duplicate processing. Those values must be declared in the **outbound data contract** and survive serialization, broker storage, replay, or adapter changes.

By contrast, an internal header such as `replyChannel` may reference a channel object existing inside one application and cannot be assumed to transfer intact to another application. Even simple headers like `traceId` appear on the receiving side only when the producer, outbound adapter, broker, and inbound adapter have compatible mapping configured.

Example of a **serialized** event envelope (this is data JSON, not a verbatim copy of `MessageHeaders`):

```json
{
  "eventId": "evt-7e1",
  "eventType": "OrderPlaced",
  "occurredAt": "2026-11-21T02:00:00Z",
  "data": {
    "orderId": "ORD-1001",
    "customerId": "CUS-08",
    "totalAmount": 350000
  }
}
```

One application might place that entire JSON as the payload and attach `traceId` in Spring headers. Another application might use its own schema, yet it must ensure that fields **required for accurate business reprocessing** are actually transmitted rather than existing only in an internal header.

### Reliability and Security Notes

- **Do not use `MessageHeaders.id` as an idempotency key across replays.** This ID belongs to a message's lifecycle; use `eventId`, a command ID, or a durably specified business key.
- **Do not trust custom headers as proof of authentication.** Headers can be spoofed, dropped during mapping, or arrive from untrusted sources. Identity and access rights must be verified by the system's security mechanisms.
- **Do not dump sensitive data into headers for logging convenience.** Headers may be recorded by monitoring tools or adapters; transmit only necessary metadata and control logging carefully.
- **Do not assume one header representation applies to every transport.** Verify serialization, header mappers, content-type conventions, and compatibility between producer and consumer.

## 6. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Putting `orderId` only in an internal header | Business key is lost when rebuilding the payload or crossing an adapter that drops headers. | Keep `orderId` in the payload/event contract. |
| Using `headers.id` as the event ID or deduplication key | Reconstructed messages can get a new ID even when representing the same event. | Issue a stable `eventId` in the data contract. |
| Using `headers.timestamp` instead of the order placement time | Resend time is mistaken for when the business event occurred. | Include a business-defined `occurredAt`. |
| Mixing `replyChannel`, `traceId`, `totalAmount` into a schemaless `Map` payload | Business logic and integration become cross-coupled; hard to type-check and evolve schemas. | Use strongly typed payloads; keep operational metadata in headers. |
| Grouping messages across all execution runs by the same `orderId` | Aggregator may combine parts that do not belong to the same split run. | Design correlation keys and group release conditions scoped appropriately. |
| Assuming retry headers are automatically present in every flow | Missing metadata or misapplied retry/idempotency policies. | Rely on explicit retry configuration and durable state when needed. |
| Treating headers as unconditionally trustworthy fields | Risk of bypassing validation or making business decisions on bad metadata. | Verify source and trust boundaries. |

## 7. Decision Guide: Where Should a Field Go?

For each field, ask yourself in sequence:

1. **If the payload is saved to a database and replayed a day later, would missing this field alter the business meaning?** If yes, that field must belong to the durable data contract.
2. **Does this field describe the order/event or only a single message transmission/processing attempt?** The former leans toward the payload/event envelope; the latter leans toward headers.
3. **Does a receiver in another application strictly require this field?** If yes, specify how it is transmitted in the schema or protocol and test the mapping; do not assume internal headers travel along automatically.
4. **Can this field change across retries, splits, transforms, or replays?** If changing is normal, it is usually unsuitable as a business identifier.
5. **Does this field involve security or personal data?** Choose transmission and access control based on trust boundaries, not mere convenience.

## 8. Scenario Exercise

An `OrderPlaced` is sent to Spring Integration for validation and splitting into line items. Classify the following:

| Field | Suggested Classification |
| --- | --- |
| `orderId = ORD-1001` | Payload: order identifier. |
| `totalAmount = 350000` | Payload: business information. |
| `occurredAt = ...` | Payload/event contract: business timestamp. |
| `eventId = evt-7e1` | Durable event contract: deduplication/replay. |
| `traceId = trace-abc` | Header: tracing across steps, with explicit boundary mapping. |
| `replyChannel` | Header: coordinating replies within the flow. |
| `sequenceNumber = 2` | Header: position of a child message produced by Splitter. |
| `correlationId = batch-41` | Header: processing group used by Aggregator, if configured with this key. |

**Open question:** If the same `ORD-1001` is reprocessed twice, would you rely on `orderId`, `eventId`, or `correlationId` to (a) prevent recording the same event twice and (b) properly group child messages of *one* split run? Hint: (a) use a stable identifier per **unit of deduplication** (`eventId` or an agreed business key); (b) use a distinct correlation per **split/aggregate group** to avoid mixing two runs.

## Summary

- **Payload** expresses the business information to be processed and is normally the part with an explicit schema that can be stored and replayed.
- **Spring message envelope** holds the payload plus **headers** for routing, correlation, replies, errors, and observability.
- **Framework message ID** differs from **business ID** and **event ID**; message creation time differs from when the business event occurred.
- **Serialized event envelope**, **Spring headers**, and **transport metadata** are three distinct layers; do not assume a header passes through every system.
- Keeping this boundary clear makes Enterprise Integration Patterns flows easier to switch transports, test, trace, and extend with minimal impact on the domain model.

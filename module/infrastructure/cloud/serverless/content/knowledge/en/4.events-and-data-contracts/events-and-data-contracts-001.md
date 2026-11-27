# Event Structure and Essential Identifier Fields

## 1. An Event Is a Data Contract

In an event-driven architecture, a producer publishes something that has happened so that consumers can react independently. For example, after an order is created, the order service emits `OrderCreated`; the inventory service can reserve stock, the analytics service updates metrics, and the notification service sends an email. Consumers can be implemented as Java functions and triggered via a queue or an event bus in a serverless environment.

An event message is therefore a contract between components. The contract must answer at least four questions: what event occurred, where it came from, which business entity it relates to, and what data the consumer needs to process it. Without identifiers or context, consumers struggle to prevent duplicate processing, trace workflows, and distinguish late-arriving events. If the payload is tightly coupled to an internal database structure, a change in the producer can break multiple consumers.

A good integration event typically has the following characteristics:

- Describes a fact that has already happened, usually named in the past tense such as `OrderCreated` or `PaymentAuthorized`.
- Has a stable identifier for the event itself, independent of delivery attempts.
- Identifies the producer source, event type, and related business entity.
- Includes the occurrence timestamp and, when needed, a version or sequence number within the entity's scope.
- Carries sufficient data for consumers according to an agreed contract.
- Is immutable after publication; business changes are represented by new events.
- Has versioning and compatibility rules so that producers and consumers can be deployed independently.

Not every database record should be treated as an integration event. `OrderCreated` expresses a business milestone; `orders_row_inserted` usually reflects only a technical detail. Consumers should depend on stable business semantics rather than the producer's table names, column names, or ORM objects.

## 2. Separating Envelope, Metadata, and Payload

A manageable structure typically has three layers:

1. **Envelope:** common fields used to identify and route the event, such as ID, source, type, and timestamp.
2. **Metadata (context):** fields that support workflow correlation, tenant, aggregate version, or tracing.
3. **Payload (business data):** event-specific information, such as order ID, customer, line items, and total amount at the time the order was created.

A simple JSON example:

```json
{
  "eventId": "01933c7e-7d8a-7a31-9a4d-2c4d9f40c101",
  "eventType": "com.example.order.created.v1",
  "source": "/commerce/orders",
  "subject": "orders/ORD-2048",
  "occurredAt": "2026-11-17T10:15:30Z",
  "schemaVersion": 1,
  "aggregate": {
    "id": "ORD-2048",
    "version": 1
  },
  "correlationId": "req-7f5a2d",
  "causationId": "cmd-4a91d0",
  "data": {
    "orderId": "ORD-2048",
    "customerId": "CUS-81",
    "currency": "VND",
    "totalAmount": 450000,
    "lines": [
      { "sku": "BOOK-01", "quantity": 2, "unitPrice": 225000 }
    ]
  }
}
```

This is an illustrative application-defined contract, not a mandatory structure across all platforms. If services need a standard format, CloudEvents can be used. Regardless of the format chosen, keep the meaning of each field consistent and document them in a schema or contract specification.

The envelope should contain information common across many event types. The payload should only contain data specific to that event type. For example, `eventId` belongs in the envelope; `totalAmount` belongs in the `OrderCreated` payload. Avoid repeating common fields in multiple places unless there is a clear compatibility reason, as the two values could diverge later.

## 3. CloudEvents: A Standard Format for the Envelope

CloudEvents is a platform-neutral specification for describing event metadata. It helps services written in different languages or running across different cloud providers exchange events with a shared understanding of source, type, and identity. CloudEvents does not dictate which business occurrences should emit events, nor does it replace a schema for the payload.

A CloudEvents version 1.0 message in JSON format may look like this:

```json
{
  "specversion": "1.0",
  "id": "01933c7e-7d8a-7a31-9a4d-2c4d9f40c101",
  "source": "/commerce/orders",
  "type": "com.example.order.created.v1",
  "subject": "orders/ORD-2048",
  "time": "2026-11-17T10:15:30Z",
  "datacontenttype": "application/json",
  "dataschema": "https://schemas.example.com/order-created/v1.json",
  "correlationid": "req-7f5a2d",
  "causationid": "cmd-4a91d0",
  "aggregateid": "ORD-2048",
  "aggregateversion": 1,
  "data": {
    "orderId": "ORD-2048",
    "customerId": "CUS-81",
    "currency": "VND",
    "totalAmount": 450000,
    "lines": [
      { "sku": "BOOK-01", "quantity": 2, "unitPrice": 225000 }
    ]
  }
}
```

In CloudEvents, the four core context attributes are:

| Attribute | Required | Meaning |
|---|---:|---|
| `specversion` | Yes | Version of the CloudEvents specification used to interpret the envelope, e.g., `1.0` |
| `id` | Yes | Event identifier within the scope of the producer source |
| `source` | Yes | URI-reference identifying the context or source that emitted the event |
| `type` | Yes | Event type, typically a namespaced name that may include a version |
| `subject` | No | The subject the event refers to within the scope of `source` |
| `time` | No | Timestamp of when the event occurred |
| `datacontenttype` | No | Content type of the data, e.g., `application/json` |
| `dataschema` | No | URI referencing the schema used to interpret the data |
| `data` | Not required on every event | Business content of the event |

The attributes `correlationid`, `causationid`, `aggregateid`, and `aggregateversion` in the example are application-defined extension attributes. CloudEvents extension names must use lowercase letters and digits. Participants must agree on the data type and meaning of extensions; merely adding an attribute to JSON does not mean every broker or SDK automatically understands it.

`specversion` and the business schema version solve two different problems. `specversion: "1.0"` tells consumers how to read the CloudEvents format. `type: "com.example.order.created.v1"` or `dataschema` tells consumers which version of the `OrderCreated` contract they are receiving. Incrementing the payload version does not necessarily require changing the CloudEvents version.

CloudEvents can be transmitted in structured mode, where metadata and data reside in the same JSON body, or binary mode, where context attributes reside in protocol metadata and the payload resides in the body. A Java function's adapter needs to know which mode the trigger provides and convert it into a consistent internal model.

## 4. Identifier Fields: Each ID Answers a Different Question

No single ID solves every need. A system must distinguish among the identifiers for the event, business entity, workflow, cause, and operation request. Overloading one ID with multiple meanings can break idempotency or distort tracing.

| Field | What Does It Identify? | Typical Scope | What Is It Used For? |
|---|---|---|---|
| `eventId` | A specific event | One event emission, stable across redeliveries | Deduplication, lookup, and auditing |
| `source` | Event source/context | A service, application, or resource | Distinguishing producers and ID namespaces |
| `aggregateId` | The modified business entity | An order, account, or subscription | Grouping events for the same entity, partitioning, and state checks |
| `aggregateVersion` | Entity version after the change | Increments per aggregate | Detecting stale, missing, or out-of-order events |
| `correlationId` | An end-to-end workflow or request | Multiple related events and calls | Finding the entire business flow |
| `causationId` | The message that directly caused the current event | A direct parent step | Building cause-and-effect chains |
| `idempotencyKey` | An operation request that must avoid repeated execution | A business action or API call | Protecting write operations or external side effects |
| `tenantId` | Customer/tenant data boundary | A tenant | Data partitioning and enforcing access control |
| `traceId` | A distributed trace | One observability trace | Linking spans across processes and services |

### 4.1. `eventId`: Identifying the Event Itself

`eventId` must be generated when the event is created and remain unchanged across all retries, redeliveries, queue transfers, or replays of that same event. If the broker delivers the same message three times, all three deliveries must carry the same identifier. If the producer creates two distinct business events, they must have different identifiers even if their payloads are identical.

With CloudEvents, the `source` and `id` pair uniquely identifies an event within the source context. IDs should be generated to be sufficiently unique across the systems exchanging events; random UUIDs or time-ordered UUIDs are common choices. Auto-incrementing database IDs can leak traffic volume and collide easily when multiple producers emit concurrently. Do not use the retry attempt count, receipt timestamp, or invocation ID as a new `eventId` when redelivering an old event.

Bad example: a consumer times out, and the producer generates a new `eventId` for the resend. The consumer cannot recognize that the two messages represent the same event and may deduct inventory or charge payment twice. Good example: the producer stores the ID alongside the outbox record; the relay resends that exact record with the same ID.

### 4.2. `aggregateId`: Identifying the Business Entity

An aggregate is a consistency boundary in the domain model. `aggregateId` identifies the entity described by the event, such as `ORD-2048`. A single order can emit multiple events: `OrderCreated`, `OrderAddressChanged`, `OrderConfirmed`, and `OrderShipped`. Each event has its own `eventId` while sharing the same `aggregateId`.

Do not use `aggregateId` in place of `eventId`: multiple events for the same order are not the same event. Nor should a customer's email or phone number be used as an aggregate ID; an ID should be stable, contain no personal data, and never change when display data changes.

In some models, an event involves multiple entities. Identify the aggregate that owns the primary change, then include any necessary related IDs in the payload with clear names such as `customerId`, `paymentId`, or `shipmentId`. Avoid using an ambiguous `id` field for multiple entities.

### 4.3. `aggregateVersion`: Order of Changes Within an Aggregate

`aggregateVersion` is the monotonically increasing version number of an aggregate after each meaningful change. For example, an order emits `OrderCreated` at version 1, `OrderAddressChanged` at version 2, and `OrderConfirmed` at version 3. Consumers can use the version to detect stale, missing, or out-of-order messages.

Version does not replace `eventId`. Two different aggregates can both be at version 2; two different events can also share the same timestamp. If a single operation emits multiple events in the same commit, establish a clear convention for whether the version applies to the aggregate state or represents a separate sequence per event. You can use `aggregateVersion` plus `eventIndex`, or a monotonically increasing `eventSequence` if consumers require a unique order per event.

Do not use timestamps as a version. Clocks across machines can drift, time resolution may be insufficient, and two events can share the same timestamp. A version number assigned by the aggregate's owner is a much more reliable basis for ordering checks.

### 4.4. `correlationId` and `causationId`

`correlationId` links multiple messages belonging to the same workflow. For example, an order creation request may lead to inventory reservation, payment, confirmation, and notification. All steps can carry the same `correlationId` to trace the entire journey of the order.

`causationId` indicates the message that directly caused the current event. When `OrderCreated` leads to `InventoryReserved`, the `causationId` field of `InventoryReserved` can be set to the `eventId` of `OrderCreated`. If an event is emitted due to a command, the value can be the ID of that command. This relationship forms a cause-and-effect chain.

These two fields are not interchangeable. A workflow may contain dozens of events sharing the same `correlationId`, while each event has a different `causationId`. When a consumer emits a new event, preserve the workflow's `correlationId` and set `causationId` to the ID of the direct input message.

### 4.5. `idempotencyKey`: Identifying an Operation Request

`idempotencyKey` is not necessarily the ID of an event. It identifies an intent or operation whose side effects should occur at most once, such as a request to capture payment for order `ORD-2048`. One operation may produce multiple events over its progression, and one event may be emitted by a relay multiple times. The idempotency key is typically stored alongside the operation result or sent to an external API if the provider supports it.

For example, when calling a payment gateway, use a stable key such as `authorize:ORD-2048:v1` across all retries of the same request. If the user actively retries payment after changing the payment method, that may be a new operation with a different key. Do not generate a new random key on each retry, as doing so defeats deduplication.

### 4.6. `tenantId`: Identifying the Customer Boundary

In a multi-tenant system, `tenantId` identifies the data space and policies of an organizational customer. Consumers must validate the tenant before reading or updating resources. Never blindly trust a `tenantId` self-declared by an external payload; the producer must derive the tenant from an authenticated context, and the consumer must enforce corresponding access controls.

If the system serves only a single tenant, there is no need to add the field just to match a template. If tenants exist, decide whether the tenant lives in a CloudEvents extension, inside the payload, or in protocol metadata, and keep the same convention across all producers and consumers. Do not use `tenantId` in place of `customerId`: one tenant may contain many customers or users.

### 4.7. `traceId` and `traceparent`

Distributed tracing links spans across API gateways, functions, queues, and external services. `traceparent` under W3C Trace Context carries the trace and parent span context; this is observability metadata. `correlationId` usually carries business meaning and can outlive a technical trace.

A long-running business workflow may exceed the retention or lifetime of a single trace or resume hours later. Therefore, do not rely solely on `traceId` to identify a business workflow. Both correlation ID and trace context can be propagated, following the platform's conventions for linking traces across asynchronous messages.

## 5. Time Fields: Occurred, Published, Received, and Processed

A message may pass through multiple queues before a consumer processes it. Having only a single `timestamp` field makes it unclear which milestone it represents. Name them explicitly:

| Field | Meaning | Who Usually Records It? |
|---|---|---|
| `occurredAt` or CloudEvents `time` | When the business change actually occurred | Business producer |
| `publishedAt` | When the event was placed onto the broker or published externally | Outbox relay or publisher |
| `receivedAt` | When the consumer or adapter received the message | Receiving system |
| `processedAt` | When the consumer finished processing | Consumer |

These milestones help measure latency: `publishedAt - occurredAt` reflects publishing lag; `processedAt - publishedAt` reflects delivery and processing latency, provided clocks are sufficiently synchronized. Do not place `receivedAt` or `processedAt` inside the immutable payload emitted by the producer; those are metadata specific to each delivery or processing attempt.

Use UTC time in ISO 8601 format, such as `2026-11-17T10:15:30Z`, and timezone-aware Java types such as `Instant`. Do not store local time strings without a timezone offset. Timestamps help with analytics and display, but should not be the sole basis for ordering events. When business ordering matters, use an aggregate-owned version or sequence.

## 6. What Should the Payload Contain?

The payload should contain enough information for consumers to fulfill their responsibilities without introducing unnecessary coupling. Two common design patterns exist:

- **Event-carried state transfer (data at occurrence time):** the payload contains a snapshot of the attributes consumers need. For example, `OrderCreated` includes the order ID, currency, total amount, and line items at creation time. Consumers can process it even if the order changes afterward.
- **Reference-based event (notification):** the payload contains an ID, and the consumer calls the data-owning service's API to fetch the current state. This reduces message size but introduces coupling to the API, access permissions, and read timing.

Choose based on semantics. If the consumer needs the exact fact as it stood at emission time, include the necessary snapshot or an immutable versioned reference. If the consumer only needs the latest state, reading from an API may make sense. Never emit an ID and expect consumers to query the producer's database directly.

Payload design principles:

- Use meaningful and consistent field names, such as `totalAmount` instead of `value`.
- Specify data types, units of measure, rounding rules, and nullability.
- For money, pass both `currency` and the amount in minor units or a decimal type with explicit conventions; never leave consumers guessing the unit.
- For quantities, specify units such as `piece`, `kg`, or `liter` if the domain supports multiple units of measure.
- Use arrays when order is meaningful; if order does not matter, consumers should not depend on element positions.
- Avoid embedding large objects or unnecessarily deep nesting.
- Never include passwords, access tokens, payment card data, or personal information that consumers do not need.
- Do not add delivery state such as `retryCount` to an immutable business event; retry counts belong in transport metadata or consumer logs.

Do not use the payload to send an ORM entity or a verbatim copy of a database table. Create a dedicated event DTO. This allows the producer to retain the freedom to evolve its storage model without altering the integration contract.

## 7. Example of an Event Sequence for an Order

Suppose order `ORD-2048` is created, inventory is reserved, and the order is confirmed. The three events may share or reference the order, while maintaining distinct event IDs and versions:

| Field | `OrderCreated` | `InventoryReserved` | `OrderConfirmed` |
|---|---|---|---|
| `eventId` | `evt-a1` | `evt-b2` | `evt-c3` |
| `type` | `order.created.v1` | `inventory.reserved.v1` | `order.confirmed.v1` |
| `aggregateId` | `ORD-2048` (Order) | `RES-9901` (Reservation) | `ORD-2048` (Order) |
| `aggregateVersion` | 1 (Order) | 1 (Reservation) | 2 (Order) |
| `correlationId` | `flow-77` | `flow-77` | `flow-77` |
| `causationId` | `cmd-91` | `evt-a1` | `evt-b2` |

In this example, `InventoryReserved` is emitted by the inventory service and belongs to its own `Reservation` aggregate. Its payload can include `orderId: ORD-2048` to link it to the order. `aggregateId` and `aggregateVersion` still describe the data owned by the inventory service. Do not assign a Reservation version to the Order aggregate simply because the two events belong to the same workflow.

Even clearer, when another service's event affects an order, keep `reservationId` in the payload, `orderId` as the related entity, and `aggregateId` identifying the aggregate owned by the producer. Field names should reflect actual data ownership boundaries, not just the overarching workflow.

## 8. Mapping Event Structure to Java

In Java, metadata and payload can be represented using immutable `record` types. The example below is an application model independent of specific adapters for AWS Lambda, Azure Functions, or another FaaS platform:

```java
import java.time.Instant;
import java.util.List;
import java.util.Objects;

public record EventMetadata(
        String eventId,
        String source,
        String type,
        String subject,
        Instant occurredAt,
        String correlationId,
        String causationId,
        String aggregateId,
        long aggregateVersion,
        String tenantId) {

    public EventMetadata {
        Objects.requireNonNull(eventId, "eventId is required");
        Objects.requireNonNull(source, "source is required");
        Objects.requireNonNull(type, "type is required");
        Objects.requireNonNull(occurredAt, "occurredAt is required");
        if (aggregateVersion < 0) {
            throw new IllegalArgumentException("aggregateVersion must be non-negative");
        }
    }
}

public record OrderLine(
        String sku,
        int quantity,
        long unitPriceMinor) {}

public record OrderCreatedData(
        String orderId,
        String customerId,
        String currency,
        long totalAmountMinor,
        List<OrderLine> lines) {

    public OrderCreatedData {
        Objects.requireNonNull(orderId, "orderId is required");
        Objects.requireNonNull(currency, "currency is required");
        lines = List.copyOf(lines);
    }
}

public record IntegrationEvent<T>(EventMetadata metadata, T data) {
    public IntegrationEvent {
        Objects.requireNonNull(metadata, "metadata is required");
        Objects.requireNonNull(data, "data is required");
    }
}
```

In this example, `totalAmountMinor` and `unitPriceMinor` represent monetary amounts in the currency's minor unit; the contract must document this convention explicitly. In systems that need decimal precision or currencies with varying fractional digits, `BigDecimal` can be used along with published scale and rounding rules. `List.copyOf` ensures the list cannot be mutated through an external reference after the event is constructed.

The adapter receiving messages from the platform must decode the envelope, validate the source, and map it to `IntegrationEvent<OrderCreatedData>`. Business logic should not depend on vendor-specific event classes unless necessary. On publish, the producer constructs metadata and payload from the same committed business change; on consume, the function validates the schema before invoking the application service.

In a Java project, each `public` type in the example is placed in its own file according to Java compilation rules. The records serve purely as the application model; the adapter is responsible for mapping JSON or CloudEvents field names to these types.

Constructor validation should not replace full schema validation. Size limits, types, required fields, element count bounds, and business invariants must all be checked. Invalid data should be classified and routed to a DLQ or quarantine workflow to avoid infinite retries.

## 9. ID Generation and Ensuring Uniqueness

Identifiers should fit the system's scope, concurrency requirements, and privacy constraints. Common options include:

| ID Generation Method | Advantages | Considerations |
|---|---|---|
| UUID v4 | Random, no central allocator needed | Not time-ordered; requires a unique constraint at the storage layer |
| UUID v7 | Includes a time component for approximate creation-time sorting | Does not replace a business sequence; do not use to infer exact ordering |
| ULID | Compact representation, lexicographically sortable by time | Still requires uniqueness rules and does not represent aggregate order |
| Database-assigned ID | Easy to use within a single database | Can create database coupling, leak scale, and be hard to coordinate across producers |

Never embed email addresses, phone numbers, customer names, or secrets inside an ID. IDs routinely appear in logs, URLs, metrics, and support tools; using personal data as an ID can unintentionally expose sensitive information. Nor should IDs encode mutable attributes such as order status or product name.

Place a unique constraint on identifier keys in the consumer's data store. Extremely low collision probability is not a reason to skip uniqueness checks. When receiving a duplicate `eventId`, the consumer should verify whether it matches the already-processed event content or represents an unexpected ID collision; do not silently treat differing payloads with the same ID as valid.

## 10. Schema, Versioning, and Compatibility

Event identifiers tell you which event type you are receiving; schemas tell you what structure the data inside has. Both must be managed together. Schemas can be stored in a repository, published via `dataschema`, or managed through a schema registry. Whatever approach is chosen, producers and consumers should run automated contract checks during build and deployment pipelines.

Key schema evolution rules:

- Prefer adding optional fields with clear default rules.
- Preserve the type, name, and semantics of published fields.
- Never reuse an old field name for a different meaning.
- Do not remove or change the type of a field while older consumers can still receive the event.
- Define how consumers handle unknown fields and missing fields.
- When introducing a breaking change, publish a new version and provide a consumer migration path.

For example, `order.created.v1` can add an optional `salesChannel` field without breaking consumers that ignore unknown fields. If `totalAmount` changes from an integer in minor units to a decimal string with different semantics, that change requires a new contract version or an explicit transformation rule.

Do not confuse schema version with `aggregateVersion`. Schema version describes the shape and meaning of the payload. Aggregate version describes the state of a business entity across mutations. A v1 schema can be used for millions of events with different aggregate versions.

## 11. Routing and Ordering: Partition Key Is Not Event ID

Event delivery platforms may support partition keys, message group IDs, or ordering keys. These keys determine how messages are partitioned or serialized. If events for the same order must be processed in sequence, `aggregateId` is typically the right choice for the partition key. That does not mean `aggregateId` replaces `eventId`; the two fields address different concerns.

Not every event bus guarantees global ordering. Some platforms guarantee order only within a partition or message group; others provide no ordering guarantee when multiple consumers execute in parallel. Consumers should still verify `aggregateVersion`, current state, and state-transition validity. If version 5 arrives while the consumer is at version 3, it can wait for version 4, re-read authoritative state, or route to a reconciliation flow per system rules.

A partition key must have a sufficiently uniform distribution. If all messages share the same key, a single partition can become a bottleneck. When business logic requires per-aggregate sequencing, partitioning by `aggregateId` generally balances intra-aggregate ordering with parallel processing across aggregates.

## 12. Transport Metadata vs. Business Metadata

A message may carry metadata added by the broker or adapter, such as delivery count, receipt handle, queue name, visibility timeout, or receive timestamp. These represent transport and operational details, not business facts. They may change across redeliveries.

Conversely, `eventId`, `source`, `type`, `occurredAt`, and the payload describe the published event itself. These values must remain stable when the same event is redelivered. `correlationId` and `causationId` represent workflow context that should be propagated across steps by shared convention.

Do not write `deliveryAttempt = 3` into the event payload and republish it as a new event. If a consumer needs to know the delivery attempt number, obtain it from trigger metadata or write it to separate logs. When bridging events across brokers, adapters may translate transport metadata while preserving the event's identity and business meaning.

## 13. Security and Privacy of Identifier Fields

IDs are often treated as purely technical data, yet they can still leak information. Sequential order numbers can reveal approximate transaction volume; IDs containing emails expose identity; tenant IDs may disclose organizational customers. Choose IDs that contain no personal data and publish only the fields consumers genuinely require.

Consumers must never treat an ID as proof of authentication or authorization. Knowing an `orderId` does not grant permission to read the order. Authorization must be enforced using workload identity, policies, and an authenticated tenant context. For events arriving from external sources, verify the origin, signature, or platform authentication mechanism before trusting the payload.

Never place access tokens, API keys, or secrets into extension attributes. Avoid logging full payloads; prefer logging IDs, event types, and processing outcomes. If a payload contains personal data, establish retention policies, encryption, access controls, and deletion handling in accordance with applicable regulations. Event immutability does not mean personal data must be retained indefinitely; design appropriate tokenization, references, or storage strategies.

## 14. Contract Validation Before Publishing and When Consuming

Producers should validate data before publishing so internal bugs do not propagate failures across multiple consumers. Consumers still need to validate on receipt because messages may originate from a different producer version, be misconfigured, or be replayed from an older archive.

Typical checks to include:

- The envelope contains all required fields; `eventId`, `source`, and `type` are non-empty.
- IDs conform to the specified format and scope; `source + id` is not reused for a different event.
- Timestamps are valid, timezone-aware, and follow the UTC convention.
- `aggregateVersion` is numeric and within a valid range if required by the event type.
- `correlationId`, `causationId`, and `tenantId` conform to system rules.
- The payload matches the schema, size limits, and core business rules.
- `currency`, units of measure, monetary amounts, and quantities have consistent semantics.
- No sensitive fields or unnecessary data are included.

When data is invalid, distinguish transient errors from contract violations. Retries cannot fix a payload missing `orderId`; such messages should be routed to a DLQ or quarantine workflow for investigation. If the schema is valid but business logic rejects the operation, emit the corresponding business outcome rather than treating it as a parse error.

## 15. Example of Identifier Handling in a Java Consumer

Consumers typically record processed events by `source` and `eventId` (or an equivalent system-defined key). The deduplication marker and business state change should reside in the same transaction when they share the same database:

```java
public interface ProcessedEventRepository {
    /** Returns true if recorded for the first time, false if the key already exists. */
    boolean insertIfAbsent(String source, String eventId);
}

public interface OrderProjectionRepository {
    void applyCreated(OrderCreatedData data, long aggregateVersion);
}

public interface TransactionRunner {
    void inTransaction(Runnable work);
}

public final class OrderCreatedConsumer {
    private final ProcessedEventRepository processedEvents;
    private final OrderProjectionRepository projection;
    private final TransactionRunner transactions;

    public OrderCreatedConsumer(
            ProcessedEventRepository processedEvents,
            OrderProjectionRepository projection,
            TransactionRunner transactions) {
        this.processedEvents = processedEvents;
        this.projection = projection;
        this.transactions = transactions;
    }

    public void handle(IntegrationEvent<OrderCreatedData> event) {
        transactions.inTransaction(() -> {
            EventMetadata metadata = event.metadata();
            boolean firstDelivery = processedEvents.insertIfAbsent(
                    metadata.source(), metadata.eventId());

            if (!firstDelivery) {
                return; // This event has already been applied successfully before.
            }

            projection.applyCreated(event.data(), metadata.aggregateVersion());
        });
    }
}
```

`insertIfAbsent` must be executed via an atomic operation such as `INSERT ... ON CONFLICT DO NOTHING` backed by a database unique constraint, not merely a read-then-write check in Java. If two serverless instances process the same message concurrently, both could read that the key does not exist yet. A unique constraint ensures only one transaction inserts the key. If updating the projection fails, the transaction must roll back the processed-event marker as well so that a subsequent retry can re-attempt processing.

This illustrates the case where the deduplication marker and projection reside in the same database. If the consumer calls an external service, a local transaction cannot be assumed to span the network call. Use an idempotency key supported by the external API, persist workflow progress state, and implement reconciliation mechanisms. Note also that the consumer should acknowledge the message only after the result has been durably persisted.

## 16. Common Design Mistakes

| Mistake | Consequence | Remedy |
|---|---|---|
| Using `orderId` as `eventId` | Every event for an order shares the same ID; consumers may drop valid events | Generate a unique event ID per event; keep order ID in aggregate/payload |
| Generating a new event ID on every retry | Duplicate deliveries cannot be recognized | Persist the ID with the outbox record and reuse it on resend |
| Using timestamp as the sole ordering mechanism | Clock skew and same-timestamp events cause misordering | Use aggregate version or sequence |
| Using `correlationId` instead of `causationId` | Direct parent-child relationships between steps cannot be reconstructed | Keep a shared correlation ID and set causation ID from the parent message |
| Putting delivery count in the immutable payload | Replays alter event content, complicating auditing | Read delivery count from broker metadata or logs |
| Putting raw database entities in the payload | Consumers become coupled to internal storage structure | Define independent event DTOs and schemas |
| Embedding email/phone numbers in IDs | Personal data leaks into logs and URLs | Use opaque IDs without personal meaning |
| Omitting a schema version | Producer payload changes can break older consumers | Manage versions and enforce compatibility checks |
| Treating knowledge of an ID as authorization | Risks cross-tenant or unauthorized resource access | Enforce permissions using identity, policies, and tenant context |

## 17. Event Contract Design Process

When defining a new event type, follow this sequence:

1. **Document the business meaning:** describe what fact occurred and under what conditions the event is emitted.
2. **Identify producer and ownership:** determine which service has authority to emit the event and which aggregate owns the change.
3. **Choose the name and type:** use a stable, namespaced name that clearly distinguishes event type and contract version.
4. **Define the envelope:** standardize event ID, source, subject, occurred time, and CloudEvents fields if used.
5. **Define linking IDs:** determine which aggregate ID/version, correlation ID, causation ID, tenant ID, and idempotency key are genuinely needed.
6. **Design the payload:** include only the data consumers need, specifying types, units, nullability, size limits, and sensitive data handling.
7. **Write schemas and examples:** publish JSON Schema, Avro, Protobuf, or an appropriate format, including both valid and invalid examples.
8. **Establish compatibility rules:** define how fields are added, types are changed, and new versions are released.
9. **Test consumers:** verify behavior for missing fields, unknown fields, duplicate deliveries, out-of-order events, replays, and invalid tenants.
10. **Monitor after deployment:** log structured IDs, measure latency, monitor DLQs, and track event versions being consumed.

## 18. Event Contract Review Checklist

- [ ] Event name describes a business fact that has occurred.
- [ ] `eventId` uniquely identifies the event and remains unchanged across retries/replays.
- [ ] `source` identifies the producer; with CloudEvents, `source + id` is unique per event.
- [ ] `type` is stable, namespaced, and follows a versioning convention.
- [ ] `subject` or `aggregateId` clearly identifies the related entity.
- [ ] `aggregateVersion` or sequence has clear semantics if ordering checks are required.
- [ ] `correlationId` and `causationId` are used for their intended purposes.
- [ ] `occurredAt` uses UTC and is distinct from publish/receive/process timestamps.
- [ ] Schema defines data types, units, nullability, and payload size limits.
- [ ] Payload does not depend directly on internal database entities or tables.
- [ ] `tenantId` and access permissions are validated in multi-tenant systems.
- [ ] No secrets or unnecessary personal data are included in the event.
- [ ] Schema validation, compatibility rules, and a version release process are in place.
- [ ] Consumers can prevent duplicate processing using durable keys and unique constraints.
- [ ] Transport metadata is separated from immutable business data.

## Conclusion

A reliable event contract separates the envelope from the payload and defines the meaning of every field clearly. `eventId` identifies the event; `source` identifies the origin; `aggregateId` and version describe the entity and order of changes; `correlationId` and `causationId` link workflows; `idempotencyKey` protects operations from repeated side effects; and trace context supports technical observability. When these fields are used for their intended purposes, Java functions can handle events more safely in the face of duplicate deliveries, delayed arrivals, and parallel scaling. Contracts must be versioned, schema-validated, data-bounded, and privacy-protected so that serverless services can evolve independently while maintaining a shared understanding of the same events.

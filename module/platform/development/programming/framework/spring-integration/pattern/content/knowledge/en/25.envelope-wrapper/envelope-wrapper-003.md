# Distinguishing Envelope from Business Payload

## 1. The Problem: One Order, Multiple Layers of Information

In an integration system, an order service sends an `OrderPlaced` event to inventory check, notification, and audit branches. The business data describes **which order, how much money, and which items**; meanwhile, the messaging system needs to know **where the event came from, which schema it follows, when it was sent, which tenant it belongs to, and which ID to use for tracing or replay**.

If all of that information is stuffed into an `OrderPlaced` DTO, the business DTO becomes coupled to the broker, tracing, routing, and retry mechanisms. Conversely, if only the payload is sent without context, consumers struggle to authenticate the source, pick the schema, deduplicate, or track down failed deliveries.

**Envelope Wrapper** is an Enterprise Integration Pattern that uses **an outer wrapper (envelope)** containing the business data (**payload**) along with metadata for inter-system communication. Separating the two layers lets the payload describe what happened or what needs to be done, while the envelope describes **how the message is identified, interpreted, protected, and transported**.

~~~mermaid
flowchart LR
    P["Order service: OrderPlaced"] --> W["Envelope Wrapper"]
    W --> E["Envelope metadata + business payload"]
    E --> B["Broker / HTTP / JMS"]
    B --> U["Unwrap + validate"]
    U --> D["OrderPlaced domain payload"]
    U --> H["Trusted routing / trace metadata"]
    D --> X["Inventory / Notification / Audit"]
    H --> X
~~~

This lesson belongs to the **Envelope wrapper** chapter in module `SPRING_INTEGRATION_PATTERN`. The module's goal is to learn to implement Enterprise Integration Patterns with Spring Integration to create loosely coupled, extensible message flows; practicing Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation, and testing/observing each processing branch.

### What Will You Be Able to Do After This Lesson?

1. State the exact boundaries between **business payload**, **application envelope**, **Spring `Message<?>`**, and **transport envelope/headers**.
2. Choose necessary metadata for event identity, schema version, source, tenant, correlation, causation, and tracing.
3. Avoid stuffing infrastructure details into domain objects or treating caller-supplied metadata as trustworthy.
4. Write Java records for domain payloads and envelopes, and implement wrap/unwrap via the Spring Integration Java DSL.
5. Control header mapping when switching transports, creating new messages, splitting/aggregating, or retrying.
6. Design schema evolution, idempotency, security, auditing, DLQ/quarantine, and replay along the proper boundaries.
7. Test that payloads are not distorted and critical metadata is not lost, duplicated, or misused.

## 2. Defining the Four Layers Precisely

### 2.1. Business Payload: Data Carrying Business Meaning

Example:

~~~json
{
  "orderId": "ORD-1001",
  "customerId": "C-17",
  "amountVnd": 850000,
  "items": [
    {"sku": "SKU-A", "quantity": 2}
  ]
}
~~~

The payload states the contents of an order. It **does not need to know** which Kafka topic, HTTP request header, or current tracing span carried the message.

A payload can also contain **business-owned** identifiers such as `orderId`, `paymentId`, or `businessVersion`; having “ID” in a field name does not automatically make it envelope metadata. The rule of thumb is: **would this field still be meaningful without a messaging system?** If it is still needed by the business domain, it likely belongs in the payload/domain contract.

### 2.2. Application Envelope: Structure Surrounding the Payload

Example of a communication contract:

~~~json
{
  "messageId": "MSG-1001",
  "eventType": "order.placed",
  "schemaVersion": 1,
  "source": "order-service",
  "tenantId": "TENANT-A",
  "occurredAt": "2026-11-21T02:30:00Z",
  "correlationId": "CHECKOUT-88",
  "causationId": "CMD-449",
  "payload": {
    "orderId": "ORD-1001",
    "customerId": "C-17",
    "amountVnd": 850000,
    "items": [
      {"sku": "SKU-A", "quantity": 2}
    ]
  }
}
~~~

This metadata can be used to select schemas, verify compatibility, attach correlation, prevent duplicates, and investigate incidents. However, **that does not mean every envelope must have all of the fields above**. Contracts must be tailored to each integration; fields lacking a clear purpose add overhead or risk leaking data.

### 2.3. Spring Integration Message: `Message<T>` Consisting of Payload and Headers

Spring Messaging models:

~~~text
Message<T>
  payload: T
  headers: MessageHeaders
~~~

Inside the JVM, a Spring `Message<OrderPlaced>` can hold the domain payload in `getPayload()` and technical metadata in headers: `MessageHeaders.ID`, `TIMESTAMP`, and application-set headers.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> message = MessageBuilder
        .withPayload("ORD-1001")
        .setHeader("eventType", "order.placed")
        .setHeader("schemaVersion", 1)
        .build();

String payload = message.getPayload(); // ORD-1001
Object type = message.getHeaders().get("eventType");
~~~

**Do not equate `MessageHeaders` with the wire application envelope.** Headers inside the JVM can carry internal objects like `replyChannel`/`errorChannel`. When crossing a broker or HTTP, adapters/header mappers may convert, drop, or regenerate headers; Spring `MessageHeaders.ID` can also change whenever a new message is built. A JSON envelope record and a Spring `Message<?>` are **two models at two different layers**, even if some fields correspond.

### 2.4. Transport Envelope: Broker or HTTP Format/Metadata

A Kafka record has a topic, partition, offset, key, headers, and value. An HTTP request has a method, path, headers, and body. JMS has its own standard headers/properties and body.

~~~text
Kafka record
  topic = orders.events
  partition = 2
  offset = 721
  key = ORD-1001
  headers = {content-type, traceparent, ...}
  value = serialized application envelope
~~~

**An offset is not a domain order version**, and **an HTTP request ID is not automatically a business event ID**. A transport may redeliver or republish the same logical event under new record coordinates.

### 2.5. Quick Comparison Table

| Artifact | What it holds | Contract owner | When can it change? |
|---|---|---|---|
| **Domain payload** | Order, payment, customer, item data. | Business/domain team. | When business rules or domain schema change. |
| **Application envelope** | Message/event identity, source, type, schema, correlation, payload. | Integration contract between producer and consumer. | When event/transport contract standards change. |
| **Spring `Message<?>`** | One payload object + `MessageHeaders` inside a Spring flow. | Framework and integration flow. | When a Transformer/adapter creates a new message or enriches headers. |
| **Transport record/envelope** | Topic/partition/offset, wire headers, request metadata. | Broker/protocol/adapter. | On every publish/delivery/retry per transport. |

### 2.6. A Layered Diagram

~~~mermaid
flowchart TB
    subgraph Transport["Transport layer: Kafka / HTTP / JMS"]
      R["Record / Request headers, offsets, routing"]
      subgraph Application["Application envelope (serialized)"]
        M["messageId, type, version, source, correlation"]
        subgraph Domain["Business payload"]
          O["orderId, amountVnd, items"]
        end
      end
    end
~~~

This diagram shows **one packaging option**, not a universal requirement for every flow. A system might pass envelope metadata in Kafka headers and serialize only the payload into the record value. Even then, an explicit contract is needed so consumers can reconstruct accurate message identity/schema after traversing the transport.

## 3. Rules for Classifying a Data Field

Ask these questions in order:

1. **Would this field exist without a broker/HTTP/messaging framework?** E.g., `orderId` and `amountVnd`: yes, so they belong to the domain.
2. **Does it describe a business fact or how the message is distributed/interpreted?** `eventType` and `schemaVersion` belong to the envelope.
3. **Is it the identifier of an operation or merely of one delivery attempt?** `paymentOperationId` is a business identity; `deliveryAttempt` is not.
4. **Who is authorized to issue/modify it?** `tenantId` may be a business attribute, yet the **trusted tenant scope** at an integration boundary must come from the principal/adapter, not blindly from the payload.
5. **Which consumers actually need it?** Do not add sensitive metadata to every envelope just because one branch might use it.

| Field | Suggested placement | Rationale |
|---|---|---|
| `orderId` | Payload | A business entity ID. |
| `amountVnd` | Payload | Business value. |
| `customerId` | Payload or protected reference | Business data with privacy requirements. |
| `eventType` | Envelope | Message type/dispatch/schema contract. |
| `schemaVersion` | Envelope | Helps consumers choose a decoder/upcaster. |
| `messageId/eventId` | Envelope, sometimes also domain event record | Stable logical-event identity; requires a unified source of truth. |
| `sourceSystem` | Envelope/trusted ingress metadata | Audit, compatibility, and provenance. |
| `correlationId` | Envelope/Spring header | Links related requests/flows. |
| `causationId` | Envelope | Causal link: which message created this message. |
| `traceparent` | Wire header/envelope per contract | Distributed tracing, not business idempotency. |
| `deliveryAttempt` | Transport/runtime diagnostics | Can increment on retry; does not belong in business payload. |
| `topic/partition/offset` | Transport metadata | Kafka coordinates, not domain fields. |
| `businessVersion` | Payload or domain event metadata | Change ordering of a business aggregate, distinct from `schemaVersion`. |
| Spring `replyChannel` object | Internal Spring message | Not a wire-portable destination. |

**Borderline case:** `tenantId` and `eventId` may appear in both the payload and the envelope due to legacy contracts or portability reasons. When they do, define **the source of truth and enforce equality checks** rather than silently preferring whichever value is convenient. A conflict between payload tenant and principal must lead to verification or rejection per policy.

## 4. Java: Modeling Domain Payload Independently from Message Transport

### 4.1. Creating Immutable Business DTOs

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

record OrderLine(String sku, int quantity) {
    OrderLine {
        if (sku == null || sku.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("INVALID_ORDER_LINE");
        }
    }
}

record OrderPlaced(
        String orderId,
        String customerId,
        BigDecimal amountVnd,
        List<OrderLine> items) {

    OrderPlaced {
        if (orderId == null || orderId.isBlank()
                || customerId == null || customerId.isBlank()
                || amountVnd == null || amountVnd.signum() <= 0) {
            throw new IllegalArgumentException("INVALID_ORDER");
        }
        Objects.requireNonNull(items, "items");
        items = List.copyOf(items);
        if (items.isEmpty()) {
            throw new IllegalArgumentException("EMPTY_ORDER");
        }
    }
}
~~~

**Observation:** `OrderPlaced` does not import `Message`, `KafkaHeaders`, Spring Integration, HTTP, or tracing. This DTO can be unit-tested as plain Java and reused in other flows without transport coupling.

In this example, constructor validation only enforces basic DTO invariants. If you need to accept invalid data for quarantine, decode into an **untrusted ingress DTO**, validate it, and only instantiate a verified `OrderPlaced` afterward. Do not catch all constructor errors and pretend “no message arrived”.

### 4.2. Generic Application Envelope

~~~java
import java.time.Instant;
import java.util.Objects;

record EventEnvelope<T>(
        String messageId,
        String eventType,
        int schemaVersion,
        String source,
        String tenantId,
        Instant occurredAt,
        String correlationId,
        String causationId,
        T payload) {

    EventEnvelope {
        if (blank(messageId)
                || blank(eventType)
                || blank(source)
                || blank(tenantId)
                || schemaVersion < 1) {
            throw new IllegalArgumentException(
                    "INVALID_ENVELOPE_METADATA");
        }
        Objects.requireNonNull(occurredAt, "occurredAt");
        Objects.requireNonNull(payload, "payload");
    }

    private static boolean blank(String value) {
        return value == null || value.isBlank();
    }
}
~~~

`EventEnvelope<T>` expresses **the contract between two services**: the envelope carries identity/type/version/provenance, while `payload` is the business data. Generics express the concept in Java, yet **do not guarantee the runtime JSON deserializer automatically knows `T`**. When receiving JSON, select the target type via event type/schema and map the payload under a safe contract.

### 4.3. Creating an Envelope Without Altering the Payload

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

OrderPlaced order = new OrderPlaced(
        "ORD-1001",
        "C-17",
        new BigDecimal("850000"),
        List.of(new OrderLine("SKU-A", 2)));

EventEnvelope<OrderPlaced> envelope = new EventEnvelope<>(
        "EVT-1001",
        "order.placed",
        1,
        "order-service",
        "TENANT-A",
        Instant.parse("2026-11-21T02:30:00Z"),
        "CHECKOUT-88",
        "CMD-449",
        order);

// envelope.payload().equals(order) == true
// envelope.schemaVersion() == 1
~~~

In production, `messageId` should be issued **once at the source of truth/outbox** and preserved when **republishing the same logical event**. If a new UUID is generated on every consumer attempt, deduplication cannot recognize it as the same event. Never reuse one `messageId` for two distinct events merely because they share an `orderId`.

## 5. An Envelope Should Not Become a “God Object”

An oversized wrapper can accumulate too much unrelated data:

~~~text
Envelope:
  payload
  58 debug flags
  raw security token
  database connection details
  client password
  internal Java MessageChannel object
  every upstream HTTP header
~~~

That stops being a useful integration wrapper and becomes an **uncontrolled data-leakage channel**. A good envelope:

- Contains **necessary, versioned metadata**.
- Enforces size limits, schemas, and allowlisted fields.
- Never copies credentials/tokens/PII when consumers do not need them.
- Contains **no internal JVM objects** that are not wire-portable.
- Has a single source of truth for identity and tenant.
- Lets the payload preserve domain semantics.
- Separates **immutable logical event metadata** from **mutable per-delivery diagnostics**.

### 5.1. Immutable Metadata vs. Per-Delivery Metadata

| Category | Examples | Preserve on broker redelivery? |
|---|---|---|
| Logical event identity | `messageId/eventId`, `eventType`, `source`, `occurredAt` | Yes, if it is the same logical event. |
| Schema contract | `schemaVersion`, encoding/content type contract | Yes, unless an explicit version conversion was recorded. |
| Business correlation | `correlationId`, `causationId` | Usually yes, per workflow contract. |
| Trusted tenant scope | `tenantId` verified against principal | Must be consistently retained/bound, never based on self-claims. |
| Delivery attempt | `deliveryAttempt`, `lastReceivedAt` | Can increment/change. |
| Broker placement | topic, partition, offset | Can change on republish. |
| Tracing runtime | `spanId`, sampling flags | May differ across consumer attempts; link traces as needed. |
| Processing state | retry count, last error, lock owner | Usually belongs to operations/state stores, not event invariants. |

**Do not overwrite `occurredAt` with “received time”** on redelivery. If you need to observe latency, add `receivedAt` or log it separately; the two timestamps answer different questions.

### 5.2. Distinguishing Schema Version from Business Version

~~~text
schemaVersion = 2
  -> how the event is encoded: which fields exist, their names, their types

orderVersion = 15
  -> state/change sequence of business order ORD-1001
~~~

An event using schema v2 **is not automatically the second change** to an order. If a Resequencer needs to order an order's events, it must use a contracted **business sequence/version**, not `schemaVersion`.

## 6. Wire Envelopes and JSON Contracts

### 6.1. JSON Is One Representation, Not the Whole Meaning of an Envelope

With Spring Integration, an envelope can travel over the wire in several ways:

**Approach A — body contains the application envelope:**

~~~json
{
  "messageId": "EVT-1001",
  "eventType": "order.placed",
  "schemaVersion": 1,
  "source": "order-service",
  "tenantId": "TENANT-A",
  "occurredAt": "2026-11-21T02:30:00Z",
  "payload": {
    "orderId": "ORD-1001",
    "customerId": "C-17",
    "amountVnd": 850000,
    "items": [{"sku": "SKU-A", "quantity": 2}]
  }
}
~~~

**Approach B — metadata in broker headers and payload in record value:**

~~~text
Kafka headers:
  event-id       = EVT-1001
  event-type     = order.placed
  schema-version = 1
  source         = order-service

Kafka value:
  {"orderId":"ORD-1001", ...}
~~~

Both approaches can work well. However, when bridging from Kafka to HTTP by copying only `value`, Approach B **loses metadata**. You need an **adapter mapping contract** to reconstruct the application envelope or forward required headers.

### 6.2. Selecting Schema and Payload Type via Allowlist

Never deserialize objects based on an arbitrary class name sent by the caller, such as:

~~~json
{"javaClass": "com.some.reflective.Class", "payload": {}}
~~~

Select from a registry/allowlist:

| `eventType` | `schemaVersion` | Target DTO |
|---|---:|---|
| `order.placed` | 1 | `OrderPlacedV1` or compatible `OrderPlaced`. |
| `order.cancelled` | 1 | `OrderCancelledV1`. |
| `payment.confirmed` | 2 | `PaymentConfirmedV2`. |

If the type/version is unsupported, return a structured error and route to an **unsupported-schema quarantine**/DLQ per policy. Do not ignore the version and force JSON into an arbitrary DTO, which can drop fields or misinterpret monetary amounts.

### 6.3. Raw and Typed Payloads Are Validated at Different Stages

~~~text
Raw bytes
  -> Content-type/size/security checks
  -> Parse wire envelope metadata
  -> Validate eventType + schemaVersion
  -> Deserialize typed payload
  -> Validate domain invariants
  -> Build Spring Message<T>
~~~

Truncated JSON fails **before** `EventEnvelope<T>` can even be constructed. An unrecognized schema fails **before** mapping the payload. A negative business amount can be decoded yet fails domain validation. These error paths require **distinct reason codes and recovery strategies**, not a single boolean “invalid”.

### 6.4. Do Not Trust `source` and `tenantId` Merely Because They Are in the Envelope

A client can send:

~~~json
{"source":"trusted-service","tenantId":"TENANT-A","payload":{}}
~~~

That is only a **claim made by the message**, not source authentication. Inbound adapters must verify signatures/mTLS/broker ACLs/principals per your architecture, then cross-check envelope metadata. If they mismatch, **reject or quarantine at the trust boundary** rather than forwarding data to the tenant claimed in JSON.

## 7. Wrap and Unwrap: Two Operations with Distinct Responsibilities

### 7.1. Wrap Creates a Contextualized Message

~~~text
Business event OrderPlaced
    + source-of-truth eventId
    + producer identity
    + schema version / occurredAt
    + authorized tenant scope
      -> EventEnvelope<OrderPlaced>
~~~

**Do not regenerate event IDs on every publish attempt.** With a transactional outbox, the original event and envelope metadata should be finalized before enqueuing; the outbox relay can re-send the **same logical event** with the same `messageId`.

Java example:

~~~java
import java.time.Instant;
import java.util.Objects;

record OrderDispatch(
        String sourceEventId,
        String sourceSystem,
        String tenantId,
        Instant occurredAt,
        String correlationId,
        String causationId,
        OrderPlaced order) {}

final class OrderEnvelopeWriter {

    EventEnvelope<OrderPlaced> wrap(OrderDispatch request) {
        Objects.requireNonNull(request, "request");
        // sourceEventId must come from an authoritative event store/outbox.
        return new EventEnvelope<>(
                request.sourceEventId(),
                "order.placed",
                1,
                request.sourceSystem(),
                request.tenantId(),
                request.occurredAt(),
                request.correlationId(),
                request.causationId(),
                request.order());
    }
}
~~~

Some systems sign/encrypt messages after serializing the envelope; others sign a canonical raw representation before sending. **Do not claim a Java object is secure simply because it is wrapped in an envelope.** Authentication, encryption, and integrity live at transport/storage boundaries and in security contracts.

### 7.2. Unwrap Validates and Converts Back to an Appropriate Payload

~~~text
Receive envelope
  -> validate authenticated source / tenant
  -> validate eventType + schemaVersion
  -> choose safe payload decoder
  -> domain validation
  -> build Spring Message<OrderPlaced> + selected headers
  -> business flow
~~~

Do not just call `envelope.payload()` and throw away all metadata. Consumers must retain **fields needed for idempotency, correlation, auditing, and tracing** in the appropriate places. At the same time, never copy all unverified input headers into the internal message.

### 7.3. Trusted Ingress Context Is a Separate Input

To illustrate the trust boundary:

~~~java
record TrustedOrderIngress(
        EventEnvelope<OrderPlaced> envelope,
        String authenticatedTenant,
        String authenticatedSource) {
    TrustedOrderIngress {
        if (envelope == null
                || authenticatedTenant == null
                || authenticatedSource == null) {
            throw new IllegalArgumentException(
                    "MISSING_TRUSTED_INGRESS_CONTEXT");
        }
    }
}
~~~

`authenticatedTenant` and `authenticatedSource` are **not** fields a sender can freely inject into JSON. In the demo, tests construct the authenticated context directly to focus on mapping. Production must derive them from broker ACLs, mTLS, signed identities, or server-side security contexts and never grant callers the right to self-assign them.

### 7.4. Header Names Belong to an Internal Contract

~~~java
final class EnvelopeHeaders {
    static final String EVENT_ID = "businessEventId";
    static final String EVENT_TYPE = "eventType";
    static final String SCHEMA_VERSION = "schemaVersion";
    static final String SOURCE = "trustedSource";
    static final String TENANT = "trustedTenant";
    static final String CORRELATION = "businessCorrelationId";
    static final String CAUSATION = "causationId";
    static final String OCCURRED_AT = "occurredAt";

    private EnvelopeHeaders() {}
}
~~~

Naming it `businessEventId` instead of `id` avoids confusion with Spring's `MessageHeaders.ID`. In projects with many message types, standardize prefixes/namespaces/allowed header types and verify them against real adapter header mappers.

### 7.5. Converter Preserves Business Payload and Selects Metadata

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class OrderEnvelopeReader {

    Message<OrderPlaced> unwrap(TrustedOrderIngress ingress) {
        EventEnvelope<OrderPlaced> envelope = ingress.envelope();

        if (!envelope.tenantId().equals(
                    ingress.authenticatedTenant())) {
            throw new SecurityException(
                    "ENVELOPE_TENANT_MISMATCH");
        }
        if (!envelope.source().equals(
                    ingress.authenticatedSource())) {
            throw new SecurityException(
                    "ENVELOPE_SOURCE_MISMATCH");
        }
        if (!"order.placed".equals(envelope.eventType())
                || envelope.schemaVersion() != 1) {
            throw new IllegalArgumentException(
                    "UNSUPPORTED_ENVELOPE_CONTRACT");
        }

        // Payload is already decoded + domain-validated in the typed example.
        MessageBuilder<OrderPlaced> builder =
                MessageBuilder.withPayload(envelope.payload())
                        .setHeader(
                                EnvelopeHeaders.EVENT_ID,
                                envelope.messageId())
                        .setHeader(
                                EnvelopeHeaders.EVENT_TYPE,
                                envelope.eventType())
                        .setHeader(
                                EnvelopeHeaders.SCHEMA_VERSION,
                                envelope.schemaVersion())
                        .setHeader(
                                EnvelopeHeaders.SOURCE,
                                ingress.authenticatedSource())
                        .setHeader(
                                EnvelopeHeaders.TENANT,
                                ingress.authenticatedTenant())
                        .setHeader(
                                EnvelopeHeaders.OCCURRED_AT,
                                envelope.occurredAt());

        if (envelope.correlationId() != null) {
            builder.setHeader(
                    EnvelopeHeaders.CORRELATION,
                    envelope.correlationId());
        }
        if (envelope.causationId() != null) {
            builder.setHeader(
                    EnvelopeHeaders.CAUSATION,
                    envelope.causationId());
        }

        return builder.build();
    }
}
~~~

**Key points to examine closely:**

1. `getPayload()` of the new message is `OrderPlaced`, **not the envelope**. Domain handlers are decoupled from the wire format.
2. `businessEventId` holds the **logical event ID** from the source. `MessageHeaders.ID` is still generated by the framework for the current message and can be a different value.
3. `trustedTenant` and `trustedSource` come from the authenticated context after matching against the envelope, never blindly copying untrusted `tenantId`/`source`.
4. `correlationId` and `causationId` are preserved when present. Do not equate them with trace IDs.
5. Only **allowlisted metadata** is copied; never copy `replyChannel`, `errorChannel`, credentials, user-supplied HTTP headers, or arbitrary Java types.

**Limitation:** In this example, `EventEnvelope<OrderPlaced>` is already typed so the payload is treated as an already decoded object. In production, deserialization/schema validation can fail **before** this type exists; an error/quarantine path is needed at the inbound adapter, as described later.

### 7.6. Do Not Confuse “Unwrapping Payload” with “Deleting Event History”

After unwrapping, the in-JVM message may hold only `OrderPlaced` and selected headers. That does not mean the original raw envelope in the source/outbox/audit store can be deleted if retention/replay requires it. The payload serves current processing, whereas **provenance** and replayability must be protected under their own policy.

## 8. Java DSL: Passing the Envelope Into the Domain Handler

### 8.1. Flow Structure

~~~mermaid
flowchart LR
    INPUT["orders.envelope.input"] --> TR["Envelope Reader / Transformer"]
    TR --> MSG["Message<OrderPlaced> + selected headers"]
    MSG --> CH["orders.domain"]
    CH --> H["Order handler"]
    TR -->|Bad type/version/tenant| ERR["Error classification / quarantine"]
~~~

This demo uses `DirectChannel`, a transformer, and a recording handler. There is no Kafka/JMS or persistent store so the exercise stays focused on the boundary between envelope and business payload.

### 8.2. Consumer Probe for Testing

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;

record ObservedOrder(
        OrderPlaced payload,
        Map<String, Object> headers) {}

final class OrderReceivedProbe {
    private final List<ObservedOrder> received =
            new CopyOnWriteArrayList<>();

    void record(
            OrderPlaced payload,
            Map<String, Object> headers) {
        received.add(new ObservedOrder(
                payload,
                Map.copyOf(headers)));
    }

    List<ObservedOrder> snapshot() {
        return List.copyOf(received);
    }
}
~~~

`OrderReceivedProbe` is an in-memory test fixture, not a domain store. `Map.copyOf(headers)` works when header values are non-null per contract. If data contains mutable objects, a shallow copy does not guarantee deep immutability; avoid storing arbitrary mutable header values.

### 8.3. Illustrative Spring Integration 6.x Configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class EnvelopeBoundaryConfiguration {

    @Bean(name = "orders.envelope.input")
    MessageChannel envelopeInput() {
        return new DirectChannel();
    }

    @Bean(name = "orders.domain")
    MessageChannel domainOrders() {
        return new DirectChannel();
    }

    @Bean
    OrderEnvelopeReader envelopeReader() {
        return new OrderEnvelopeReader();
    }

    @Bean
    OrderReceivedProbe orderReceivedProbe() {
        return new OrderReceivedProbe();
    }

    @Bean
    IntegrationFlow unwrapEnvelopeFlow(OrderEnvelopeReader reader) {
        return IntegrationFlow.from("orders.envelope.input")
                .transform(
                        TrustedOrderIngress.class,
                        reader::unwrap)
                .channel("orders.domain")
                .get();
    }

    @Bean
    IntegrationFlow consumeDomainOrders(OrderReceivedProbe probe) {
        return IntegrationFlow.from("orders.domain")
                .handle(
                        OrderPlaced.class,
                        (payload, headers) -> {
                            probe.record(payload, headers);
                            return null; // Terminal demo handler.
                        })
                .get();
    }
}
~~~

**Note on types:** a Spring Integration transformer can return a `Message<?>` as the transformation output. In this flow, `reader.unwrap(...)` returns `Message<OrderPlaced>` containing the payload and selected internal headers; the next handler receives `OrderPlaced` as its payload. If using another mapper/transformer or a different Java DSL version, verify how the framework **merges/propagates headers** in an integration test rather than testing only the plain Java return value.

**Scope Note:** STEP 4 only authors the lesson. The code is illustrative of Spring Integration 6.x; no build or Content QA has been executed against the project's dependency versions.

### 8.4. Why Not Use `envelope.toString()` as a Wire Payload?

A Java record's `toString()` is not a stable JSON contract, nor does it guarantee escaping, compatibility, or security. For wire transport, use a serializer with an explicit schema/configuration, checking field allowlists, canonicalization when signing, size limits, and converter versions.

### 8.5. What Should the Domain Handler Receive?

Two common choices:

~~~java
void handle(OrderPlaced payload) {
    // Business logic only needs the order.
}
~~~

or:

~~~java
void handle(OrderPlaced payload, String businessEventId) {
    // Business operation needs stable event identity for deduplication.
}
~~~

It is not necessary to force domain handlers to accept the entire `EventEnvelope<OrderPlaced>`. If a handler needs idempotency, pass an **intentional identity** at an application service boundary rather than making every domain object aware of Kafka headers or Spring Messaging APIs.

## 9. JUnit 5: Envelope and Payload Must Stay Separate

### 9.1. Deterministic Test Fixture

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

final class EnvelopeTestData {

    static OrderPlaced order() {
        return new OrderPlaced(
                "ORD-1001",
                "C-17",
                new BigDecimal("850000"),
                List.of(new OrderLine("SKU-A", 2)));
    }

    static EventEnvelope<OrderPlaced> envelope() {
        return new EventEnvelope<>(
                "EVT-1001",
                "order.placed",
                1,
                "order-service",
                "TENANT-A",
                Instant.parse("2026-11-21T02:30:00Z"),
                "CHECKOUT-88",
                "CMD-449",
                order());
    }

    static TrustedOrderIngress trustedIngress() {
        return new TrustedOrderIngress(
                envelope(), "TENANT-A", "order-service");
    }
}
~~~

### 9.2. Wrapping Does Not Alter the Original Payload

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotSame;

class OrderEnvelopeWriterTest {

    @Test
    void wrappingAddsContextButKeepsBusinessFields() {
        OrderPlaced original = EnvelopeTestData.order();
        EventEnvelope<OrderPlaced> wrapped =
                new OrderEnvelopeWriter().wrap(
                        new OrderDispatch(
                                "EVT-1001",
                                "order-service",
                                "TENANT-A",
                                EnvelopeTestData.envelope().occurredAt(),
                                "CHECKOUT-88",
                                "CMD-449",
                                original));

        assertEquals(original, wrapped.payload());
        assertEquals("order.placed", wrapped.eventType());
        assertEquals(1, wrapped.schemaVersion());
        assertEquals("TENANT-A", wrapped.tenantId());
        assertNotSame(original, wrapped);
    }
}
~~~

What needs testing is that **payload fields and the object contract remain intact**, not that `OrderPlaced` and `EventEnvelope` share a Java type. `assertNotSame` in the example simply emphasizes that they are two objects of different layers.

### 9.3. Unwrap Returns Domain Payload and Keeps Selected Metadata

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class OrderEnvelopeReaderTest {

    @Test
    void unwrappingBuildsMessageWithBusinessPayload() {
        Message<OrderPlaced> message =
                new OrderEnvelopeReader().unwrap(
                        EnvelopeTestData.trustedIngress());

        assertEquals(
                EnvelopeTestData.order(),
                message.getPayload());
        assertEquals(
                "EVT-1001",
                message.getHeaders().get(
                        EnvelopeHeaders.EVENT_ID));
        assertEquals(
                "TENANT-A",
                message.getHeaders().get(
                        EnvelopeHeaders.TENANT));
        assertEquals(
                "CHECKOUT-88",
                message.getHeaders().get(
                        EnvelopeHeaders.CORRELATION));
        assertEquals(
                "CMD-449",
                message.getHeaders().get(
                        EnvelopeHeaders.CAUSATION));
        assertNotNull(
                message.getHeaders().get(MessageHeaders.ID));
    }
}
~~~

This test does **not** assert that `MessageHeaders.ID` equals `EVT-1001`. On the contrary, it checks **logical event identity** in the application header `businessEventId`, while the framework keeps its own ID for the current message.

### 9.4. Tenant Mismatch Must Be Blocked Before Business Handling

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;

class EnvelopeTenantSecurityTest {

    @Test
    void claimedTenantCannotOverrideAuthenticatedTenant() {
        TrustedOrderIngress forged = new TrustedOrderIngress(
                EnvelopeTestData.envelope(),
                "TENANT-B",
                "order-service");

        assertThrows(SecurityException.class, () ->
                new OrderEnvelopeReader().unwrap(forged));
    }
}
~~~

This example tests **string comparison inside the converter**. Production must ensure `authenticatedTenant` genuinely comes from the security layer. If a test passes `authenticatedTenant` from a self-declared field inside the same envelope, the test only proves two strings matched, not authorization.

### 9.5. Wrong Event Type or Schema Version Must Reject

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertThrows;

class EnvelopeContractTest {

    @Test
    void unknownVersionDoesNotSilentlyUseV1Decoder() {
        EventEnvelope<OrderPlaced> valid =
                EnvelopeTestData.envelope();
        EventEnvelope<OrderPlaced> version2 = new EventEnvelope<>(
                valid.messageId(),
                valid.eventType(),
                2,
                valid.source(),
                valid.tenantId(),
                valid.occurredAt(),
                valid.correlationId(),
                valid.causationId(),
                valid.payload());

        TrustedOrderIngress incoming = new TrustedOrderIngress(
                version2, "TENANT-A", "order-service");

        assertThrows(IllegalArgumentException.class, () ->
                new OrderEnvelopeReader().unwrap(incoming));
    }
}
~~~

In a real application, whether version 2 is supported is decided by the **schema registry/decoder policy**. The demo allows only V1 to show that **versions must never be silently ignored**.

### 9.6. Code Should Not Mint a New Message ID to Deduplicate

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SameBusinessEventTwoMessageInstancesTest {

    @Test
    void rebuiltSpringMessageStillHasSameLogicalEventIdentity() {
        OrderEnvelopeReader reader = new OrderEnvelopeReader();
        TrustedOrderIngress incoming =
                EnvelopeTestData.trustedIngress();

        Message<OrderPlaced> first = reader.unwrap(incoming);
        Message<OrderPlaced> retry = reader.unwrap(incoming);

        assertEquals(
                first.getHeaders().get(
                        EnvelopeHeaders.EVENT_ID),
                retry.getHeaders().get(
                        EnvelopeHeaders.EVENT_ID));
        assertEquals(
                first.getPayload(),
                retry.getPayload());

        // Framework MessageHeaders.ID may be newly issued.
        // Do not use it as a business idempotency key.
    }
}
~~~

## 10. Integration Test: Messages Traverse Java DSL According to Contract

### 10.1. End-to-End Test Inside a Spring Context

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(EnvelopeBoundaryConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class EnvelopeBoundaryIntegrationTest {

    @Autowired
    @Qualifier("orders.envelope.input")
    MessageChannel input;

    @Autowired
    OrderReceivedProbe probe;

    @Test
    void domainHandlerSeesOrderNotApplicationEnvelope() {
        boolean dispatched = input.send(
                MessageBuilder.withPayload(
                        EnvelopeTestData.trustedIngress())
                        .build());

        assertTrue(dispatched);

        List<ObservedOrder> seen = probe.snapshot();
        assertEquals(1, seen.size());
        assertEquals(
                EnvelopeTestData.order(),
                seen.get(0).payload());
        assertEquals(
                "EVT-1001",
                seen.get(0).headers().get(
                        EnvelopeHeaders.EVENT_ID));
        assertEquals(
                "TENANT-A",
                seen.get(0).headers().get(
                        EnvelopeHeaders.TENANT));
        assertEquals(
                "CHECKOUT-88",
                seen.get(0).headers().get(
                        EnvelopeHeaders.CORRELATION));
    }
}
~~~

**What the test proves:** through the Transformer and channel, the handler receives `OrderPlaced` as payload and selected metadata in headers.

**What the test does not prove:** JSON codecs, Kafka/JMS header mappers, persistence, broker redelivery, real principal authorization, or transactions. Those belong to boundary-specific tests.

### 10.2. Prevent Spoofed Sources from Entering the Domain Flow

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(EnvelopeBoundaryConfiguration.class)
class EnvelopeSourceMismatchIntegrationTest {

    @Autowired
    @Qualifier("orders.envelope.input")
    MessageChannel input;

    @Autowired
    OrderReceivedProbe probe;

    @Test
    void forgedSourceDoesNotReachDomainHandler() {
        TrustedOrderIngress incoming = new TrustedOrderIngress(
                EnvelopeTestData.envelope(),
                "TENANT-A",
                "other-service");

        // The messaging layer may wrap SecurityException in
        // MessageHandlingException; assert broad error here.
        assertThrows(RuntimeException.class, () ->
                input.send(
                        MessageBuilder.withPayload(
                                incoming).build()));
        assertEquals(0, probe.snapshot().size());
    }
}
~~~

To test exact **reason codes and error routes**, inspect the cause chain and apply the specific adapter's error policy. Do not write tests that merely expect an exception while ignoring **where the failed event will be retained**.

### 10.3. Do Not Assert Immediately When Processing Is Async

With `DirectChannel`, the handler in the demo runs synchronously according to channel semantics. With `ExecutorChannel`, `QueueChannel`, pollers, or brokers:

- `send(...)` may only confirm dispatch/enqueueing, not business completion.
- Use `CountDownLatch`/`BlockingQueue.poll(timeout)` or deadline-based awaiting.
- Clean up executors/latches and never rely on `Thread.sleep` as proof of processing.
- Also test late retries, process restarts, and delivery metadata mapping if production requirements depend on them.

## 11. Header Mapping Across Adapters

### 11.1. Spring Headers Do Not Automatically Appear on the Wire

In Spring Integration, `businessEventId` may exist in a `Message<OrderPlaced>`. When an outbound adapter sends the message to Kafka, JMS, or HTTP, the **header mapper/serializer** decides which headers are transmitted, under what names, and with what data types. The receiving inbound adapter may reconstruct a Spring message with a **different ID**.

~~~mermaid
flowchart LR
    A["Spring Message: payload + headers"] --> M1["Outbound Header Mapper"]
    M1 --> W["Broker record"]
    W --> M2["Inbound Header Mapper"]
    M2 --> B["New Spring Message: payload + mapped headers"]
~~~

Never assume all headers automatically survive across every transport, especially custom headers, Java objects, or non-serializable types.

### 11.2. Mapping Table to Govern

| Internal header / metadata | Suggested wire representation | Action on receipt |
|---|---|---|
| `businessEventId` | `event-id` string/bytes per contract | Validate format and identity; use for deduplication. |
| `eventType` | `event-type` | Check allowlist/type registry. |
| `schemaVersion` | `schema-version` | Select decoder version. |
| `trustedSource` | Sender identity authenticated by adapter, matched against claimed source | Never treat a self-declared string as authenticated. |
| `trustedTenant` | Authenticated tenant scope, transport-dependent | Bind from principal and validate. |
| `businessCorrelationId` | `correlation-id` | Propagate per workflow contract. |
| `causationId` | `causation-id` | Build causal graph/audit. |
| `occurredAt` | ISO-8601/epoch per schema | Parse timezone/precision consistently. |
| Spring `MessageHeaders.ID` | Do not copy as business ID name | Framework may generate a new one. |
| `replyChannel`/`errorChannel` objects | Never serialize JVM objects | Use verified wire reply destinations/routing. |

If the system chooses a **JSON body envelope** instead of wire headers, logical fields can live in the body while only transport-essential metadata goes in headers. What matters is **a clear, consistent contract with round-trip tests**.

### 11.3. A Common Anti-Pattern

~~~text
Sender:
  message.headers["businessEventId"] = EVT-101
  message.payload = OrderPlaced

Outbound broker adapter:
  serializes payload to JSON
  does not map businessEventId

Receiver:
  gets OrderPlaced without event ID
  generates a new UUID on every receipt

Consequence:
  broker redelivers -> new UUID -> deduplication fails
~~~

Diagnosis should not start with “add retries to the receiver”, but by checking **at which adapter boundary metadata was dropped**.

### 11.4. Content Type and Serialization Are Two Different Things

`content-type=application/json` only specifies the encoding format, which is not enough to identify the business schema. You also need:

- Which `eventType`?
- Which `schemaVersion`?
- How are `BigDecimal`, timestamps, and enums represented in JSON?
- Are unknown fields ignored, rejected, or logged?
- What are the size/depth limits and validation rules?
- Is the payload encrypted/signed, and which portion is signed?

Never use `Content-Type` as a substitute for `eventType`/`schemaVersion`.

### 11.5. Round-Trip Tests at Real Adapters

An integration test should verify:

~~~text
Given:
  EventEnvelope<OrderPlaced> messageId=EVT-101,
  schemaVersion=1, tenant=TENANT-A, correlation=CHECKOUT-9

When:
  outbound adapter serializes + publishes
  inbound adapter deserializes + rebuilds Spring Message

Then:
  OrderPlaced business values unchanged
  businessEventId remains EVT-101
  type/version present and validated
  trusted tenant is derived and matched
  correlation preserved
  no internal Java MessageChannel serialized
~~~

Spring `MessageHeaders.ID` **is not required** to remain identical across adapters. When the contract requires stable event identity, assert `businessEventId` or wire envelope `messageId`.

## 12. Correlation, Causation, Tracing, and Idempotency Are Not Synonymous

### 12.1. One Business Workflow Has Many Events

~~~text
Checkout CHECKOUT-88
  |
  +-- CMD-449: PlaceOrder
      |
      +-- EVT-1001: OrderPlaced
          |
          +-- EVT-1002: InventoryReserved
          |
          +-- EVT-1003: NotificationRequested
~~~

In this model:

- **Correlation ID** `CHECKOUT-88` groups messages within one workflow.
- **Causation ID** of `EVT-1001` can be `CMD-449`; of `EVT-1002` can be `EVT-1001`.
- **Logical event ID** distinguishes each event.
- **Trace ID** links spans/logs across a distributed execution run.
- **Business operation ID** identifies the side-effecting operation to deduplicate, e.g., `RESERVE-STOCK:ORD-1001`.

### 12.2. Do Not Use Correlation as the Sole Idempotency Key

Suppose every event has `correlationId=CHECKOUT-88`. If Notification and Inventory use `correlationId` as their deduplication key, the second branch could be flagged as a duplicate of the first.

Suitable scopes include:

~~~text
Inventory consumer: (TENANT-A, INVENTORY_RESERVE, RESERVE-ORD-1001)
Notification consumer: (TENANT-A, NOTIFY_ORDER_PLACED, EVT-1001)
Audit consumer: (TENANT-A, AUDIT, EVT-1001)
~~~

These are illustrative keys. No single default key fits every domain; derive keys from **logical operation/event identity** within the consumer's boundary.

### 12.3. Message IDs Can Differ Across Deliveries

~~~text
Logical event envelope:
  messageId = EVT-1001

First Spring Message:
  headers.id = UUID-A

Broker redelivery / reconstructed Spring Message:
  headers.id = UUID-B

Business effect:
  should be applied only once for EVT-1001
~~~

Do not confuse **Spring message identity** with **logical event identity**. On duplicate delivery, an endpoint may process two Spring messages while still applying only one business operation.

### 12.4. Causation ID Does Not Replace Event ID

Two events emitted from the same parent can have:

~~~text
InventoryReserved.eventId = EVT-1002
InventoryReserved.causationId = EVT-1001

NotificationRequested.eventId = EVT-1003
NotificationRequested.causationId = EVT-1001
~~~

If you deduplicate by causation ID, the second event would be dropped mistakenly. Causation asks “**what led to this event?**”, not “**is this the exact same event?**”.

### 12.5. Trace Context Is Telemetry, Not Authorization

`traceparent` or `traceId` can traverse multiple services, yet:

- Never use it as an authentication token.
- Never attach customer PII arbitrarily to baggage/tracing.
- Sampling can drop spans; never treat traces as durable audits.
- Retries can create child spans or new traces; rely on business event/operation IDs to reconstruct accurate history.

## 13. Envelope Wrapper with Router and Filter

### 13.1. Which Field Should a Router Inspect?

A Router can choose a channel by:

~~~text
Envelope.eventType = "order.placed"
  -> orderEventsChannel

Envelope.eventType = "payment.confirmed"
  -> paymentEventsChannel
~~~

However, `eventType` must be **validated against a schema/allowlist and trusted source**. If a caller can alter it, an invalid message could route into the wrong handler.

After unwrapping, there are two patterns:

1. **Route before unwrapping** using the wire envelope's validated type/version, then select a typed decoder.
2. **Unwrap/normalize first** via a schema registry, then route by typed payload or selected header.

Never route into a business handler solely based on a matching `eventType` name when the body has not yet been decoded/validated.

### 13.2. Payload-Based Routing Can Also Be Valid

For instance, all messages are `OrderPlaced`, yet international and domestic orders follow different branches. This is business routing that can inspect a **validated payload field** like `shippingCountry` if the domain includes it. There is no need to duplicate every business attribute into the envelope.

### 13.3. Filter Should Not Silently Drop Malformed Envelopes

If `schemaVersion` is missing or `tenantId` mismatches, that is a contract/security error requiring error/quarantine or rejection per policy. Calling `filter(false)` without a discard route can cause messages to vanish silently.

~~~mermaid
flowchart TD
    E["Incoming Envelope"] --> V{"Type/version/security validation"}
    V -->|Valid| U["Unwrap"]
    U --> F{"Business Filter"}
    F -->|Accepted| B["Business"]
    F -->|Rejected| Q1["Business quarantine/rejection"]
    V -->|Unsupported/malformed| Q2["Schema/security error path"]
~~~

Do not confuse **invalid envelope metadata** with a **rejected business payload**. For example, a wrong schema version is a compatibility error; a negative amount is business validation. Remediation, ownership, and retry behavior differ.

### 13.4. Envelope Can Be Lost When a Filter/Transformer Returns Only the Payload

Example:

~~~java
// In Java terms, this is a simple unwrap step:
OrderPlaced order = envelope.payload();
~~~

If this runs mid-flow without creating new headers or preserving metadata in an application context, downstream steps lose `eventId`/`correlationId`. That can starve Idempotent Receiver and tracing of needed data. Write integration tests checking metadata at **the actual point of consumption**, not just at ingress.

### 13.5. Header Enrichment Must Not Become Data Laundering

Adding a `trustedTenant` header copied from `envelope.tenantId` and forwarding it **does not make the tenant trusted**. Header enrichment merely moves data; security must be verified from the principal/adapter. Only name a header “trusted” after cross-checking/authorization has completed.

## 14. Splitter, Aggregator, and Resequencer: Do Not Misuse Envelope IDs

### 14.1. Splitter Produces Multiple Child Messages from One Parent Payload

An `OrderPlaced` has two line items. Splitter can generate:

~~~text
Parent envelope:
  messageId=EVT-1001
  payload=OrderPlaced(items=[SKU-A, SKU-B])

Child messages:
  childEventId=EVT-1001/LINE-1, payload=OrderLine(SKU-A)
  childEventId=EVT-1001/LINE-2, payload=OrderLine(SKU-B)
~~~

These are **two distinct child operations/messages**, even though both originate from parent `EVT-1001`. If both keep `messageId=EVT-1001` under a global dedup key, the second child will be treated as a duplicate of the first.

An illustrative identity model:

~~~java
record OrderLineWork(
        String orderId,
        int lineNumber,
        OrderLine line) {}

record SplitChild(
        String childEventId,
        String parentEventId,
        String batchCorrelationId,
        int sequenceNumber,
        int sequenceSize,
        OrderLineWork payload) {}
~~~

IDs/sequences must be defined so they can be **reproduced deterministically across retries/replays**, such as storing child IDs at the producer/outbox or deriving them from canonicalized contract identities. Never mint fresh UUIDs each time Splitter reruns if downstream needs to deduplicate child operations.

### 14.2. Do Not Copy “the Same ID” on Every Fan-Out

There are two distinct semantics:

| Scenario | Reasonable message identity | Idempotency scope |
|---|---|---|
| **Publish–Subscribe** delivers the **same event** `EVT-1001` to Audit and Notification. | Same logical event ID, multiple consumers. | `consumerId + EVT-1001`. |
| **Splitter** creates **two child operations** from one parent. | Each child has its own identity, sharing parent/causation. | `batchId + childId` or distinct operation ID. |

Confusing the two leads to broken deduplication. Neither “every new message must get a new ID” nor “every branch must keep one ID” applies universally; distinguish **copies of the same event from new logical events/commands**.

### 14.3. Correlation, Sequence, and Business Event Identity

~~~text
batchCorrelation = BATCH-1001-RUN-7
childEventId     = EVT-1001-LINE-2
sequenceNumber   = 2
sequenceSize     = 3
~~~

`batchCorrelation` groups child messages. `sequenceNumber` restores position. `childEventId` detects duplicate children. They do not substitute for one another.

If one child is dropped by a Filter as invalid, the Aggregator may wait forever expecting `sequenceSize=3`. Emit a placeholder/failure outcome, define a partial release policy, or quarantine the whole batch per business contract, rather than silently altering `sequenceSize` on a remaining child.

### 14.4. Aggregator Should Not Blindly Stuff Whole Envelopes Into the Business Result

Suppose three child replies arrive:

~~~text
Reply A: envelope(meta A, payload=ReservationResult)
Reply B: envelope(meta B, payload=ReservationResult)
Reply C: envelope(meta C, payload=ReservationResult)
~~~

The Aggregator needs to know how to build a **business aggregate result**, such as `OrderReservationSummary`, and when emitting a **new logical result event**, issue appropriate event ID/version/correlation metadata. Do not simply concatenate three JSON envelopes into an array and call it a business DTO unless downstream actually contracts for it.

### 14.5. Resequencer Uses Business Sequence, Not Schema Version

~~~text
Order ORD-1001:
  Event A: businessSequence=1, schemaVersion=2
  Event B: businessSequence=2, schemaVersion=2
  Event C: businessSequence=3, schemaVersion=3
~~~

To emit A→B→C, the Resequencer must use `businessSequence` and the proper correlation/group identity, not `schemaVersion=2,2,3`. An envelope is only a **carrier for metadata**; it does not define their semantics.

### 14.6. Releasing in Order Does Not Guarantee Committing in Order

After a Resequencer, an `ExecutorChannel` or multi-consumer broker can process messages concurrently. Commit order can still invert even if release order was right. When business invariants require ordered commits per version, use per-key serialization/partitioning, optimistic version guards, idempotency, and transactions where side effects occur.

## 15. Scatter–Gather, Publish–Subscribe, and Recipient List

### 15.1. Fan-Out Does Not Mean Duplicating Business Work

~~~mermaid
flowchart TD
    E["Envelope EVT-1001: OrderPlaced"] --> PUB["Publish–Subscribe"]
    PUB --> A["Audit consumer"]
    PUB --> N["Notification consumer"]
    PUB --> I["Inventory consumer"]
    A --> KA["Inbox key: audit/EVT-1001"]
    N --> KN["Inbox key: notify/EVT-1001"]
    I --> KI["Inbox key: inventory/EVT-1001"]
~~~

The same original envelope can reach three recipients. Each recipient needs to process the event once **for its own responsibility**. Never use a global `processed_messages[eventId]` table that blocks all other recipients after Audit finishes first.

### 15.2. Scatter Requests Outcomes for Distinct Tasks

A `PriceQuoteRequested` request may generate:

~~~text
REQUEST-9
  -> Supplier A quote
  -> Supplier B quote
  -> Supplier C quote
~~~

The parent envelope's `correlationId=REQUEST-9` lets Gatherer group replies, yet each recipient needs separate ID/attempt tracking to distinguish **two replies from Supplier A** from **one reply from Supplier B**.

Here metadata like `recipientId`, `parentRequestId`, `attemptId`, and deadlines can live in the envelope or process store. Never treat an in-JVM `replyChannel` object as a stable wire address when suppliers reply from separate services.

### 15.3. Failure in One Branch Must Not Corrupt the Final Outcome

If the Fraud branch receives an invalid schema while Inventory and Pricing succeed, Gatherer must not report `APPROVED` if Fraud is mandatory. Model **branch outcomes** with `SUCCESS/INVALID/ERROR/TIMEOUT` states and explicit correlation; never embed a failed envelope inside an aggregate payload and silently treat it as success.

## 16. Gateway and Request–Reply

### 16.1. An Envelope Describes the Request, While the Reply Is a New Message

~~~text
Request:
  messageId=CMD-101
  eventType=inventory.reserve.requested
  correlationId=CHECKOUT-88

Reply:
  messageId=EVT-202
  eventType=inventory.reservation.completed
  correlationId=CHECKOUT-88
  causationId=CMD-101
~~~

These are two logical messages; they **do not have to share the same `messageId`**. Correlation/causation links the reply back to the originating request while preserving each message's own identity.

### 16.2. Spring `replyChannel` Is an Internal Return Path

Inside a synchronous internal Gateway, Spring Integration can use `replyChannel` to return the result. This is a **technical header holding a channel object or internal return address**, not something transmitted over Kafka/HTTP by default.

When requests go to external services:

- Use a transport-defined reply destination (protected reply topic/queue/callback URL), if needed.
- Keep a stable `requestId`/`correlationId` to match asynchronous replies.
- Never deserialize arbitrary `replyChannel` objects from untrusted JSON.
- Enforce timeouts, validate authorization, and filter late replies.

### 16.3. Caller Timeout Does Not Mean the Operation Never Ran

~~~text
T0 Gateway sends request
T1 Worker receives and succeeds
T2 Reply is lost on transport
T3 Gateway times out
T4 Caller retries the same operation
~~~

Retries must preserve the **business operation ID**, consult the ledger/receipt, and avoid new side effects if the previous operation already committed. A new envelope created merely to **re-deliver** the same operation must not turn into a new operation via a randomly generated ID.

### 16.4. Discards or Quarantines Must Have a Response Contract

If an incoming envelope is invalid and a Filter discards it, a Gateway waiting for a reply may time out. For synchronous APIs, define an explicit response:

~~~json
{
  "requestId": "CMD-101",
  "status": "REJECTED",
  "reasonCode": "UNSUPPORTED_SCHEMA_VERSION",
  "quarantineReference": "Q-202"
}
~~~

**Do not assume `discardChannel` automatically sends a reply.** Design explicit error/response flows; avoid returning raw input or secrets in error messages. For asynchronous event ingestion, you may ack only once the quarantine record is durably saved per contract.

## 17. Claim Check: Envelopes Do Not Replace a Payload Store

### 17.1. Envelope Wrapper and Claim Check Solve Different Problems

| Pattern | Purpose | Data that keeps moving |
|---|---|---|
| **Envelope Wrapper** | Adds metadata/protocol around a payload. | Envelope containing or referencing the payload per contract. |
| **Claim Check** | Stores the original payload/message in a store and sends a small token. | Claim ID/reference, requiring retrieval when used. |

An envelope can carry `payloadRef` instead of the full payload:

~~~json
{
  "messageId": "EVT-1001",
  "eventType": "order.placed",
  "schemaVersion": 1,
  "payloadRef": "CLAIM-555"
}
~~~

However, **a payload reference does not automatically make the original payload available**. Consumers must be authorized and have access to the store/retention window to retrieve it. If the token expires before a retry, envelope metadata remains readable while the business payload is gone.

### 17.2. Do Not Replace Business Event ID with Claim ID

If the same event is replayed under a new claim:

~~~text
Original logical event: EVT-1001
Attempt 1 claim: CLAIM-555
Attempt 2 claim: CLAIM-777
~~~

Both claims can simply be two ways to retrieve the same event; deduplicate business side effects by `EVT-1001`/appropriate operation ID, not by the newly created claim token.

### 17.3. Metadata Has a Lifecycle Too

Envelopes may be retained longer than claims or vice versa. Define retention and cleanup policies for:

- Raw envelope/event logs.
- Payload object/Claim Check stores.
- Inbox idempotency records.
- Audits/receipts.
- Transport DLQs and replay references.

If a payload is deleted for security/compliance reasons, a remaining envelope/tombstone cannot reconstruct the data. Never “replay” by guessing missing content.

## 18. Retry, Error Channel, DLQ, and Quarantine

### 18.1. An Invalid Envelope Is Not Always an Invalid Business Payload

| Scenario | Error layer | Handling direction |
|---|---|---|
| JSON/Avro/Protobuf cannot decode | Wire serialization/converter | Adapter error handling, raw reference + DLQ/quarantine. |
| Missing `eventType` or unsupported `schemaVersion` | Application envelope contract | Quarantine/unsupported-schema workflow. |
| Envelope `tenantId` conflicts with authenticated principal | Security/provenance | Reject, security audit; do not auto-retry. |
| Valid envelope but negative `amountVnd` | Domain validation | Business-invalid quarantine/rejection. |
| Duplicate `eventId` already `COMPLETED` | Delivery/idempotency | Return previous outcome/ack duplicate per contract. |
| External database timeout | Infrastructure | Retry/backoff/possibly DLQ; do not label payload invalid. |
| Insufficient inventory for business order | Business outcome | Rejected outcome/compensation; not necessarily a “bad message”. |
| Replay encounters expired claim | Payload retrieval/lifecycle | Reconcile/authorized reissue; do not fabricate payload. |

**Key takeaway:** Validating an envelope does not prove business processing succeeded. Likewise, a downstream failure does not make the original envelope malformed.

### 18.2. Error Paths Can Occur Before the Spring Integration Flow

~~~mermaid
flowchart TD
    B["Broker / HTTP raw bytes"] --> DE{"Decode envelope?"}
    DE -->|No| RAW["Adapter error/DLQ"]
    DE -->|Yes| SE{"Schema + provenance valid?"}
    SE -->|No| Q["Envelope quarantine/rejection"]
    SE -->|Yes| UN["Unwrap typed business payload"]
    UN --> VA{"Domain validation"}
    VA -->|Invalid| BUSQ["Business-invalid quarantine"]
    VA -->|Valid| H["Business handler"]
    H -->|Technical failure| ER["Retry/error channel/recovery"]
~~~

Spring Integration's `errorChannel` operates according to execution context and endpoint/adapter configuration. Not every Kafka/JMS deserialization failure or HTTP binding error automatically lands on the **global `errorChannel`**; those failures can happen before a `Message<?>` is even constructed.

### 18.3. Fields to Retain in Error Records

~~~text
event=ENVELOPE_REJECTED
  transportRef=orders.events/partition-2/offset-721
  authenticatedSource=order-service
  trustedTenant=TENANT-A
  eventRef=EVT-1001 (if readable)
  eventType=order.placed (if readable)
  declaredSchemaVersion=7
  errorCode=UNSUPPORTED_SCHEMA_VERSION
  rawPayloadReference=protected-ref
  decoderVersion=v3
  receivedAt=...
~~~

This is an **application-suggested audit/error schema**, not a log format automatically emitted by the framework. Never log full raw bodies containing customer data or tokens. For undecodable payloads, an `eventId` inside the body may be **untrustworthy or absent**, so retain stable transport references and authenticated source details for investigation.

### 18.4. Retries Must Preserve Logical Identity

~~~text
Attempt #1:
  envelope.messageId = EVT-1001
  broker deliveryAttempt = 1

Attempt #2:
  envelope.messageId = EVT-1001
  broker deliveryAttempt = 2
~~~

When **redelivering the same event**, `messageId` should stay unchanged. A message produced by a genuine **business correction** may need a new event ID and a `causationId` pointing to the original; distinguish corrections from transport retries.

### 18.5. Do Not Fake “At-Least-Once” by Adding Retry Count to the Payload

`retryCount` is attempt/recovery metadata, not a business fact of `OrderPlaced`. Putting it inside the domain DTO can cause consumers to treat each attempt as a new event and alter fingerprints. Use delivery metadata or durable operation state; keep `OrderPlaced` immutable across retries of the same logical event.

### 18.6. Durable Outbox Prevents Dangling Envelopes

If a producer saves order state to the DB and then publishes an envelope to a broker, a mid-flight crash can create **a committed order with no emitted event**, or duplicate publishes if an ack is lost. One solution is:

~~~mermaid
flowchart LR
    CMD["Place Order"] --> TX["DB transaction"]
    TX --> ORDER[("Orders")]
    TX --> OUTBOX[("Outbox event + envelope metadata")]
    OUTBOX --> RELAY["Publisher/retry"]
    RELAY --> B[("Broker")]
    B --> INBOX["Idempotent consumer"]
~~~

Outbox records should keep **logical event ID, type, schema version, source, and payload/version reference** stable; the relay can republish the same envelope. Consumers still need idempotency because **duplicate publishing is a real possibility**, not a bug eliminated outright by an outbox.

## 19. Security and Integrity of Envelopes

### 19.1. A Wrapper Is Not a Natural Security Boundary

If JSON contains:

~~~json
{
  "tenantId": "TENANT-A",
  "source": "payment-service",
  "payload": {"orderId": "ORD-9"}
}
~~~

that is just caller-supplied data. There is no proof `source` or `tenantId` is accurate until the adapter authenticates and binds permissions. **An envelope can be modified, spoofed, or replayed** without appropriate transport, authentication, and integrity controls.

### 19.2. Protecting Source and Scope

1. Authenticate producers via mTLS, broker ACLs, service identity, or an approved mechanism.
2. Bind `tenantId` to the authenticated principal/route; never use a self-declared tenant to access another tenant's data.
3. Validate `eventType`, `schemaVersion`, and whether the source is permitted to emit that type.
4. Bound body size, nesting depth, item counts, header counts, and header lengths.
5. Use encryption in transit and at rest per data classification; never treat base64 as encryption.
6. Never let wire-provided arbitrary Java class/type discriminators drive the deserializer.
7. If using signatures/MACs, define the signed **canonical bytes** and version; never verify one representation and parse a different substitutable representation.
8. During replay, check revocations, retention, and permissions **at replay time**, not just at initial receipt.

### 19.3. Header Injection and Overrides

An inbound HTTP request might send arbitrary headers named `trustedTenant` or `errorChannel`. If the application blindly copies them into Spring headers and downstream trusts them:

- Callers can spoof tenants.
- Inject route selectors/headers to divert into unintended channels.
- Expose or hijack reply/error routes.
- Push disallowed data types into stores/logs.

Solution: **allowlist + normalize + validate + derive privileged headers from trusted context**. Never copy `replyChannel`/`errorChannel` from the wire without strict protocol and security contracts.

### 19.4. Metadata Security Matters as Much as Payload Security

Metadata can leak business facts:

~~~text
source = hospital-service
eventType = cancer-treatment.updated
customerId = ...
correlationId = patient-...
~~~

Even if the body is encrypted, improper metadata still leaks sensitive information. For sensitive domains, avoid IDs containing emails, national IDs, or medical conditions; use opaque IDs and minimize exposed fields. **Never put `eventId`/`tenantId`/`customerId` into high-cardinality or PII-exposing metric labels.**

### 19.5. Do Not Log Entire Envelopes by Default

A better production log:

~~~text
event=ENVELOPE_ACCEPTED
  eventType=order.placed
  schemaVersion=1
  eventRefHash=...
  source=order-service
  outcome=ACCEPTED
~~~

If inspecting original raw payloads is necessary, use a secure audit/object store with access controls, retention, and checksums rather than printing full payloads into log text or exceptions. Deserializer stack traces can also contain body fragments; configure redaction.

## 20. Schema Evolution: Envelope Version Differs from Business Payload Version

### 20.1. One Event Type Can Have Multiple Schema Revisions

Example `order.placed` version 1:

~~~json
{
  "eventType": "order.placed",
  "schemaVersion": 1,
  "payload": {
    "orderId": "ORD-101",
    "amountVnd": 100000
  }
}
~~~

Version 2 might add `currency`:

~~~json
{
  "eventType": "order.placed",
  "schemaVersion": 2,
  "payload": {
    "orderId": "ORD-101",
    "amount": 100000,
    "currency": "VND"
  }
}
~~~

This is an example of a **schema change**. Never read V2 as V1 and silently ignore `currency` without confirming semantics; some changes require migration/upcasters or rejection if the decoder does not yet support them.

### 20.2. Upcasters Must Be Intentional Transformations

One model:

~~~text
Wire V1 -> decode OrderPlacedV1 -> upcast to canonical OrderPlaced
Wire V2 -> decode OrderPlacedV2 -> upcast to canonical OrderPlaced
                                  |
                                  v
                           Domain handler
~~~

An upcaster can supply defaults according to **approved business rules**, never by fabricating missing facts. For example, only if historical contracts guarantee all V1 orders used VND can you upcast `currency=VND`. If currency is unknown, reject/quarantine/enrich rather than guessing.

### 20.3. Do Not “Change” Identity After Upcasting

Upcasting the **representation of the same event** must not generate a new event ID and trick Idempotent Receiver into treating an old event as unprocessed.

~~~text
Original:
  eventId=EVT-55, schemaVersion=1

Upcast view:
  eventId=EVT-55, canonicalPayloadVersion=2
~~~

If the producer emits **a new business correction event**, that is a different situation: it needs a new event ID, causation/reference to the original, and explicit operation semantics.

### 20.4. Reader/Writer Compatibility

| Scenario | What to verify |
|---|---|
| New consumer reads old event | Is the V1 decoder still supported? Does the upcaster preserve business semantics? |
| Old consumer receives new event | Is forward/backward compatibility supported, or must it reject? |
| Enum adds a new value | Unknown enum values handled explicitly, never silently mapped to success. |
| Field renamed/type changed | Migration validated; no silent drops. |
| Money scale/currency changed | No unit or precision errors. |
| Timestamp precision/timezone changed | Consistent conversion preserving `occurredAt`. |
| New event type | Router/registry allowlisted; never routed blindly. |
| Persisted messages across deploy | Old serialization remains readable through the store/replay horizon. |

### 20.5. Event Metadata Needs a Version Contract Too

Not only the payload schema changes; how `eventType`, `tenantId`, `correlationId`, or `messageId` are structured can change across envelope standards. For major revisions, consider separating **`envelopeFormatVersion`** from **event payload `schemaVersion`** alongside a migration plan. Do not overload one version field to represent three independent meanings simultaneously.

## 21. Observability: Knowing Where a Message Lost a Layer of Information

### 21.1. Milestones Worth Recording

~~~text
event=TRANSPORT_RECORD_RECEIVED
  transportRef=orders.events/2/721
  sourceAuthenticated=true

event=ENVELOPE_DECODED
  businessEventRef=EVT-1001
  eventType=order.placed
  schemaVersion=1

event=ENVELOPE_VALIDATED
  businessEventRef=EVT-1001
  tenantMatch=true
  typeSupported=true

event=BUSINESS_PAYLOAD_UNWRAPPED
  businessEventRef=EVT-1001
  payloadType=OrderPlaced

event=BUSINESS_HANDLER_COMPLETED
  businessEventRef=EVT-1001
  operationRef=RESERVE-ORD-1001

event=BROKER_ACKNOWLEDGED
  transportRef=orders.events/2/721
~~~

This is a **suggested log schema**, not a log set automatically provided by Spring Integration in every configuration. Nor do these events always have a one-to-one relationship: one broker record may hold a batch of events, or the same event may be delivered multiple times.

### 21.2. Do Not Collapse “Success” Milestones

| Milestone | What it confirms | What it does not confirm |
|---|---|---|
| Transport accepted | Broker/adapter accepted the record per contract. | Consumer processed it. |
| Envelope decoded | Wire metadata/payload representation parsed successfully. | Source/tenant authorized. |
| Envelope validated | Type/version/provenance passed policy. | Business payload is valid. |
| Payload unwrapped | Typed domain payload ready for downstream. | Payment/inventory side effects committed. |
| Handler returned | One processing callback finished under the execution model. | External transactions persisted without proof. |
| Inbox COMPLETED | Authoritative operation receipt recorded in ledger. | All external systems atomic outside ledger bounds. |
| Broker acked | Transport recorded acknowledgment. | No further replays/DLQs/manual republishes can occur. |

A dashboard reporting “processed” right after envelope parsing can be dangerously misleading. Define explicitly: **processed = decoded? validated? handled? committed?**

### 21.3. Suggested Metrics

| Metric | Purpose |
|---|---|
| `envelope_received_total{source}` | Number of envelopes received. |
| `envelope_decoded_total{type,version}` | Successful decodes. |
| `envelope_decode_failed_total{reason}` | Decode failures before business flow. |
| `envelope_contract_rejected_total{reason}` | Invalid type/version/format. |
| `envelope_source_mismatch_total` | Claimed source differs from authenticated source. |
| `envelope_tenant_mismatch_total` | Tenant boundary violations. |
| `envelope_unwrapped_total{type}` | Typed payloads successfully unwrapped. |
| `envelope_header_mapping_failed_total{adapter}` | Metadata lost or unmappable across adapter. |
| `envelope_schema_upcast_total{from,to}` | Version migrations executed. |
| `envelope_duplicate_delivery_total` | Logical events redelivered by identity. |
| `envelope_quarantined_total{reason}` | Envelopes quarantined per policy. |
| `envelope_size_bytes` | Distribution of envelope sizes. |
| `envelope_processing_latency_seconds` | Latency from ingress to a defined milestone. |

These are **suggested names**, without claiming the framework creates them automatically. Avoid putting `messageId`, `orderId`, `customerId`, `traceId`, or emails in high-cardinality metric labels. Use authorized logs/traces/audits to inspect individual events.

### 21.4. Message History Does Not Replace Durable Auditing

Spring Integration Message History (when enabled) shows which components a message passed through. However, it does not automatically:

- Save the raw wire envelope when adapter decoding fails.
- Prove raw payload signatures/authorization were valid.
- Maintain a durable mapping between business `eventId` and operation receipts.
- Record broker/DB transactions or acknowledgements.
- Retain metadata dropped by a misconfigured adapter header mapper.

Combine **broker coordinates, envelope event IDs, secure payload references, message history, trace context, and business receipts**.

## 22. Diagnosing When a Consumer Has Payload but Lost Metadata

Suppose the Inventory Handler receives the right `OrderPlaced` but cannot find `businessEventId` or `correlationId`.

1. **Check the producer:** were `eventId`/correlation issued and saved stably in the outbox?
2. **Check the serialized envelope:** is metadata in the body or headers? Are field names/types exact?
3. **Check the outbound adapter:** does the header mapper allowlist the needed fields? Does it drop unknown headers?
4. **Check the broker:** what do the record value and wire headers actually contain? Is there a different record ID due to republishing?
5. **Check the inbound adapter:** which fields are deserialized, and which are placed into Spring headers?
6. **Check trust rules:** were producer/source/tenant authenticated? Was a header stripped by security policy?
7. **Check the Transformer:** did it return a plain payload while dropping selected metadata?
8. **Check the Router/Filter:** did a default route send the message to the wrong handler? Was metadata altered across branches?
9. **Check the Splitter:** were child IDs and correlation/sequence generated accurately?
10. **Check the Gateway:** did a reply try to use an internal channel object across a transport hop?
11. **Check retries:** did the same logical event get assigned a new ID on a consumer attempt?
12. **Check audit/tracing:** were `eventRef`, `transportRef`, traces, and business receipts cross-referenced to pinpoint the drop?
13. **Add a regression test:** execute a wire round-trip and assert selected headers after the inbound adapter, not only before outbound.

### 22.1. Familiar Symptoms

| Symptom | First possibility to check |
|---|---|
| Spring Message ID changes across Kafka | May be normal; distinguish Spring ID from logical event ID. |
| Duplicate side effects after redelivery | `businessEventId`/operation key lost or missing durable deduplication. |
| Consumer reads wrong DTO | `eventType`/`schemaVersion` unmapped or decoder fell back to wrong default. |
| Tenant mismatches spike after deploy | Header mapping, principal scope, or claimed metadata changed. |
| Correlation disappears at Aggregator | Transformer/Splitter/header mapper dropped correlation headers. |
| Kafka value is right but headers are missing | Outbound mapper did not serialize custom headers. |
| Gateway times out even though handler ran | Reply routing/return address is not wire-portable. |
| Resequencer emits out of order | Using `schemaVersion` or arrival order instead of business sequence. |
| Replaying an event with an old schema fails | Old decoder/upcaster was removed earlier than retention allows. |
| Quarantine lacks `eventId` | Raw parsing failed; rely on transport reference and secure raw copy. |

### 22.2. Systematic Debugging Sequence

~~~text
Producer business event
  -> Application envelope
  -> Serialized bytes + wire headers
  -> Inbound adapter / header mapper
  -> Spring Message<?> received
  -> Envelope unwrap/validation
  -> Domain handler + operation receipt
~~~

Find **the first point where metadata is lost or changes meaning**. Never fix it by copying all HTTP/broker headers into the domain handler: that can leak untrusted values into the business flow and create security vulnerabilities.

## 23. Test Matrix: Envelopes Differ from Business Payloads

| ID | Input/scenario | Expected outcome | What must not happen |
|---|---|---|---|
| EW-01 | Wrap valid `OrderPlaced` | Envelope holds exact payload and metadata. | Payload values change. |
| EW-02 | Unwrap valid typed envelope | `Message<OrderPlaced>` with selected headers. | Domain handler receives raw JSON envelope. |
| EW-03 | Envelope with stable event ID | `businessEventId` matches source. | Mistakenly overwritten with Spring `MessageHeaders.ID`. |
| EW-04 | Two Spring messages for same logical event | Same business event ID, equivalent payload. | Treated as two new operations because UUIDs differ. |
| EW-05 | Two different events sharing `orderId` | Two distinct event IDs. | Deduplicated by `orderId` alone. |
| EW-06 | Envelope missing `messageId` | Reject/validation failure. | Minting a new UUID per retry without auditing. |
| EW-07 | Envelope missing `eventType` | Reject as invalid contract. | Routed to a default handler. |
| EW-08 | Unsupported `schemaVersion` | Quarantine/unsupported-schema handling. | Arbitrarily parsed as V1. |
| EW-09 | Claimed tenant differs from authenticated tenant | Security rejection. | Accessing another tenant's data. |
| EW-10 | Claimed source differs from authenticated producer | Security rejection/audit. | Accepting a spoofed source. |
| EW-11 | Envelope contains raw HTTP credential | Redact/drop per policy. | Forwarding secrets to subscribers. |
| EW-12 | JSON body envelope over Kafka | Header/body mapping keeps required metadata. | Consumer copies only payload and loses type/version. |
| EW-13 | Metadata in Kafka headers, value holds payload only | Inbound adapter reconstructs identity/schema. | Losing `eventId` silently. |
| EW-14 | Spring custom header unmapped outbound | Test catches missing header. | Silent metadata loss. |
| EW-15 | Unserializable wire header | Error/validation per adapter policy. | Serializing arbitrary Java objects. |
| EW-16 | Wire sends `replyChannel` object | Reject/ignore; use transport reply destination. | Unauthorized Java channel deserialization. |
| EW-17 | Malformed JSON before typed decoder | Adapter error route/raw quarantine. | Claiming typed Filter handled it. |
| EW-18 | Negative payload amount despite valid envelope | Business validation rejection. | Treating valid envelope as business success. |
| EW-19 | External DB timeout after unwrap | Technical retry/recovery. | Labeling the envelope malformed. |
| EW-20 | Broker ack lost after business commit | Same event identity, idempotent result. | Repeating business side effects. |
| EW-21 | Outbox relay publishes event twice | Same logical `eventId`. | Relay creating a new business event. |
| EW-22 | Same event republished at different offset | Deduplicated by event ID/operation ID. | Deduplicating solely by offset. |
| EW-23 | One event fanned out to Audit and Notification | Each consumer processes once. | Global dedup blocking the second branch. |
| EW-24 | Splitter creates three child messages | Unique child IDs, stable parent/sequence metadata. | All three sharing one operation key and dropping children. |
| EW-25 | Filter drops one child | Aggregator applies failure outcome/timeout policy. | Hanging forever unnoticed. |
| EW-26 | Aggregator receives duplicate reply | Deduplicated by recipient/child identity. | Duplicate substituting for missing child. |
| EW-27 | Scatter–Gather receives late reply | Correlation + attempt/version guard. | Merging reply into a new request. |
| EW-28 | Resequencer sees `schemaVersion=2` across group | Ordered by business sequence. | Ordering by `schemaVersion`. |
| EW-29 | Gateway request timeout | Stable `operationId`, outcome reconciliation. | Creating a new charge due to a new request ID. |
| EW-30 | Claim Check reissues claim | Same business event identity if same logical event. | Deduplicating by the new `claimId`. |
| EW-31 | `occurredAt` from producer differs from `receivedAt` | Both timestamps keep their meanings. | Overwriting `occurredAt` with received time. |
| EW-32 | Retry attempt 2 | `deliveryAttempt` may increment; logical `eventId` unchanged. | Modifying payload/domain event per delivery. |
| EW-33 | External `traceparent` supplied | Trace context validated/propagated per policy. | Treating trace ID as authorization or operation ID. |
| EW-34 | Correlation and causation differ | Both fields keep their semantics. | Deduplicating siblings by causation ID. |
| EW-35 | V1 event read by V2 consumer | Upcast per business contract or reject clearly. | Guessing missing data without basis. |
| EW-36 | V2 introduces currency | Validate/convert per schema. | Silently dropping currency. |
| EW-37 | Object store keeps raw envelope after deploy | Old schema still decodes/replays within retention. | Losing replay capability. |
| EW-38 | Oversized wire body | Size/depth bounds, error route. | OOM or log flooding. |
| EW-39 | Payload contains PII, metadata logged | Redacted structured logs. | Logging raw customer details/tokens. |
| EW-40 | Caller spoofs tenant header | Trusted context validation. | Assuming a header named “trusted” is verified. |
| EW-41 | `MessageHeaders.ID` changes across Transformer | `businessEventId` still suffices for idempotency. | Relying on runtime ID as source of truth. |
| EW-42 | Unknown `eventType` | Quarantine/controlled rejection. | Deserializing caller-specified arbitrary classes. |
| EW-43 | Schema registry/downstream unavailable | Technical error/retry policy. | Assuming payload is definitely invalid. |
| EW-44 | No reply for discarded request | Explicit Gateway response/error contract. | Caller hanging until timeout for no reason. |
| EW-45 | Transport message accepted, business effect fails | Metrics separate received/handled/committed. | Reporting COMPLETED at ingress. |
| EW-46 | Producer source changes after deploy | Authenticated source allowlist updated with audit. | Accepting solely because claimed source looks familiar. |
| EW-47 | Header mapper changed between two services | Round-trip test catches dropped/retyped fields. | Trusting pure in-JVM serialization tests. |
| EW-48 | Original message received a correction | New event/attempt lineage and operation policy. | Overwriting old `eventId` to pretend data never changed. |

### 23.1. Testing at the Right Layer

| Layer | What to test | What it does not prove |
|---|---|---|
| **Java unit** | Wrap/unwrap, DTO invariants, type/version/tenant validation. | Broker header mapping or durable state. |
| **Spring Integration test** | Transformer, channel, handler, selected headers. | JSON codec/Kafka behavior without real adapters. |
| **Serializer/contract test** | JSON fields, schema registry, version compatibility. | Broker delivery/acks. |
| **Adapter integration test** | Inbound/outbound header mapping, content type, raw parse errors. | Domain side-effect commits if mocked. |
| **Persistence test** | Outbox/inbox, idempotency, transactions, replay compatibility. | Remote payments outside the transaction. |
| **System/chaos test** | Restarts, duplicates, late replies, concurrency, DLQ replay. | Every conceivable production condition. |
| **Security test** | Source/tenant auth, header injection, payload size, PII redaction. | Untested trust boundaries. |

### 23.2. A Golden Round-Trip Fixture

For an event identified as `EVT-1001`, maintain a fixture containing:

~~~text
messageId: EVT-1001
eventType: order.placed
schemaVersion: 1
source: order-service
tenantId: TENANT-A
correlationId: CHECKOUT-88
causationId: CMD-449
payload.orderId: ORD-1001
payload.amountVnd: 850000
payload.items[0].sku: SKU-A
~~~

Tests should pass the fixture through **serialize → transport adapter mapping → deserialize → unwrap → handler observation**. Assert all meaningful fields remain intact, and verify that **intentionally unforwarded fields** such as credentials or `replyChannel` objects are excluded.

## 24. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| “The envelope is the domain payload.” | Domain DTO accumulates trace/broker-specific fields. | Separate domain event from application envelope. |
| “Spring `MessageHeaders` are identical to the wire envelope.” | Breaks when switching transports or deserializing. | Build a mapping contract and round-trip tests. |
| “Every ID is `messageId`.” | Confuses operation, trace, correlation, and delivery. | Define each identity by purpose. |
| “`MessageHeaders.ID` must stay unchanged across Kafka.” | Broken tests or unstable deduplication. | Maintain a separate logical event ID. |
| “`schemaVersion` is the event order.” | Resequencer outputs in the wrong order. | Use business sequence/order version. |
| “`correlationId` suffices to deduplicate every child.” | Splitter/gatherer drops valid children. | Use child operation IDs and consumer scopes. |
| “Wrapping is encryption/security.” | Trusts spoofed data, leaks secrets. | Implement AuthN/AuthZ, integrity, and encryption separately. |
| “Having `tenantId` in JSON means it's trusted.” | Cross-tenant access. | Bind from the authenticated principal. |
| “A header named `trustedSource` means it's verified.” | Data laundering via header enrichment. | Validate before creating trusted metadata. |
| “Forwarding only the payload is enough.” | Event ID, schema, and correlation lost across adapters. | Deliberately map selected metadata. |
| “Forward all headers just to be safe.” | Leaks secrets, route injection, and JVM objects. | Allowlist and sanitize. |
| “Deserializer automatically knows every event class.” | Injection/type confusion/schema bugs. | Type/version allowlist. |
| “Unknown schema? Just try deserializing V1.” | Lost fields, wrong currency units. | Reject or upcast under contract. |
| “`occurredAt` = `receivedAt`.” | Wrong latency metrics and replay chronology. | Keep the two timestamps separate. |
| “Retries should mint a new event ID each time.” | Deduplication stops working. | Stable logical event ID for redeliveries. |
| “Unwrapped means processed successfully.” | Reports success before business commit. | Track side-effect state/receipts. |
| “Wrapping a payload externally gives you Claim Check.” | No store/token/retrieval semantics. | Distinguish Envelope Wrapper from Claim Check. |
| “Gateway `replyChannel` objects can travel over the wire.” | Lost replies or unsafe deserialization. | Use wire reply destinations/protocols. |
| “Message History is the business receipt audit.” | Does not prove commit/idempotency. | Durable inbox/outbox/receipts plus tracing. |
| “Logging entire envelopes is easiest for debugging.” | PII/secret leaks and storage blowups. | Redact and use protected payload references. |
| “Fan-out with one event ID should only run one consumer.” | Audit/Notification/Inventory lost. | Consumer-scoped idempotency. |
| “Replay corrections keep all metadata identical.” | Unclear whether data changed or who edited it. | New revision/causation/attempt lineage. |
| “One writer/reader unit test proves the adapter works.” | Headers dropped over the network. | Adapter/contract/system tests. |

## 25. Practice Exercises

1. **Layer information:** given JSON containing `orderId`, `eventId`, `traceId`, `amountVnd`, `schemaVersion`, and `deliveryAttempt`, explain which belongs to payload, envelope, or transport, and why.
2. **Domain DTO:** write `OrderPlaced` without importing Spring/Kafka/HTTP, validating basic invariants and `items` immutability.
3. **Generic envelope:** implement `EventEnvelope<T>` with message ID, type, version, source, tenant, `occurredAt`, correlation, causation, and payload.
4. **Wrap:** create `OrderEnvelopeWriter` accepting `OrderDispatch` from a trusted source and returning an envelope without generating a new ID per attempt.
5. **Unwrap:** convert `EventEnvelope<OrderPlaced>` into Spring `Message<OrderPlaced>` while keeping selected headers.
6. **Logical vs. framework ID:** unwrap the same event twice; assert `businessEventId` matches without relying on `MessageHeaders.ID`.
7. **Schema validation:** change version 1 to version 99; the converter must reject with a reason instead of silently decoding V1.
8. **Tenant binding:** envelope claims `TENANT-A` while trusted context is `TENANT-B`; verify the domain handler is never called.
9. **Source binding:** claimed source and authenticated source mismatch; verify failure and audit.
10. **Header allowlist:** attempt to pass arbitrary headers `replyChannel`, `secret`, and `debugPayload` onto the wire; only allowlisted fields survive mapping.
11. **Java DSL flow:** use `EnvelopeBoundaryConfiguration` to send a `TrustedOrderIngress` and observe `OrderReceivedProbe`.
12. **Raw codec:** add a JSON parser/serializer matching your dependencies and test decoding envelope metadata before mapping the typed payload.
13. **Adapter round-trip:** send an envelope through a real Kafka/JMS/HTTP test setup and verify custom headers and payload survive inbound mapping.
14. **Malformed wire:** submit malformed JSON and verify the adapter error route runs even though the typed Transformer is never invoked.
15. **Domain invalid:** send a valid envelope carrying a negative amount in the raw ingress DTO; ensure it fails as business validation, not unsupported schema.
16. **EventId stability:** simulate the outbox publishing the same logical event twice with different transport coordinates; Idempotent Receiver still recognizes the duplicate.
17. **Consumer scopes:** send the same `OrderPlaced` to Audit and Notification; both process once under consumer-scoped keys.
18. **Splitter:** split `OrderPlaced` into `OrderLineWork` items with distinct child IDs, keeping parent/correlation/sequence accurate and stable across replays.
19. **Aggregator:** send the same child reply twice while omitting another child; the group must not release as if complete.
20. **Resequencer:** create three events with business sequences 1, 2, 3 yet different `schemaVersion` values; order by business sequence, not schema version.
21. **Gateway:** create request/reply envelopes with separate event IDs, shared correlation, and reply causation pointing to request ID; test caller timeout and late reply.
22. **Claim Check:** replace the payload inside the envelope with a protected claim reference; test expired claims and business idempotency on reissue.
23. **Upcasting:** create `OrderPlacedV1`/`V2`, defaulting currency only when historical business contracts prove it, preserving the original event ID across upcasting.
24. **Security:** attempt source/tenant spoofing via HTTP headers and envelope body; catch mismatches before business routing without leaking receipts.
25. **Observability:** produce `ENVELOPE_DECODED`, `ENVELOPE_VALIDATED`, and `BUSINESS_HANDLER_COMPLETED` logs with redacted IDs and separate metrics per milestone.
26. **Replay runbook:** document the path from DLQ/secure raw store to schema upcaster, validation, idempotency ledger, and audited business handler.
27. **Compatibility matrix:** verify a new consumer reads V1 and V2 envelopes or returns an explicit unsupported error when incompatible.
28. **Partial transport failure:** simulate a successful publish where the producer misses the ack; replay keeps the event ID and the consumer does not duplicate side effects.
29. **Header loss regression:** disable `businessEventId` mapping in the outbound adapter in a test and verify the round-trip test fails meaningfully.
30. **Data retention:** when a payload must be deleted upon expiration, retain authorized minimal metadata and a tombstone if policy requires guarding against late duplicates.

### 25.1. Criteria for a Passing Exercise

- Domain payload **does not depend on** header names, brokers, or service adapters.
- Envelope defines **logical event identity** and an explicit schema contract.
- Unwrap **validates source/tenant/type/version** before handing off to the business flow.
- Spring `MessageHeaders.ID` and envelope `messageId` **are never conflated**.
- Selected headers survive adapter round-trips; untrusted headers are stripped.
- Retries preserve event/operation identity with idempotency at the right side-effect boundary.
- Splitter, Aggregator, Router, Gateway, Claim Check, and Resequencer use correlation/sequence semantically accurately.
- Unsupported schema, malformed raw data, domain invalid, and technical failures follow distinct error paths.
- Metadata/PII are protected, and logs/metrics do not expose unnecessary data.
- Tests verify **where metadata can actually be lost** — especially outbound/inbound adapters.

## 26. Self-Check Questions

**Q1: What is Envelope Wrapper?**

It is a pattern that wraps a business payload in communication contract metadata, conveying identity, type/version, provenance, correlation, and processing context without turning domain DTOs into transport objects.

**Q2: Is the payload all of the data inside the JSON?**

No. A JSON body can hold both the application envelope and the payload. The payload is the data carrying business meaning; envelope metadata describes the message and transport contract.

**Q3: Is a Spring `Message<?>` the same as a JSON envelope?**

Not necessarily. A Spring Message is an in-JVM object containing payload and headers; a JSON envelope is a wire/application representation. Explicit mapping is required when converting between them.

**Q4: If Spring's message ID changes after a Transformer, did the event change?**

Not by default. One logical event can be represented by multiple Spring messages; the business event ID can remain unchanged across them.

**Q5: How do `orderId` and `eventId` differ?**

`orderId` is a business entity ID; `eventId` is the identity of one logical event. A single order can have many events.

**Q6: Should `schemaVersion` be used by a Resequencer for ordering?**

No. It describes the format/contract version, not business change order. A separate business sequence/version is required.

**Q7: Why not use `correlationId` as the idempotency key for every message?**

Because multiple child events/operations can share a correlation group. Deduplication usually binds to the logical event or business operation and consumer scope.

**Q8: How do `causationId` and `correlationId` differ?**

Causation links a message to its direct cause; correlation groups messages belonging to the same workflow/request. Two sibling events can share causation while having distinct IDs.

**Q9: If an envelope has `tenantId=TENANT-A`, is the tenant authenticated?**

No. You must verify principal/adapter identity and bind/cross-check it against the claimed metadata.

**Q10: Why not forward all Spring headers over Kafka to avoid losing information?**

Because many headers are internal JVM objects, secrets, or untrusted data; some cannot even be serialized. Map only selected fields under a validated contract.

**Q11: What if `schemaVersion` is unsupported?**

Reject or route to an unsupported-schema quarantine/error path per policy; never arbitrarily deserialize into a default schema and drop fields.

**Q12: Will a malformed JSON message pass through a typed Filter?**

No, if the adapter/decoder fails before constructing a typed message. Adapter-specific error handling is required.

**Q13: Is fanning out the same event to Audit and Notification a duplicate?**

Not within each consumer's scope. It is the same event needing two independent side effects; each consumer should process it once.

**Q14: When a Splitter creates three child messages, should they keep the same child event ID?**

No, if they represent three distinct logical child operations. Preserve parent/causation/correlation properly, while assigning distinct, stable child identities.

**Q15: Should a Gateway reply share the same `eventId` as the request?**

Not by default. The reply is a distinct logical message that can have a new ID while keeping correlation and causation/request ID to link back to the originating request.

**Q16: Does an envelope containing `payloadRef` mean Claim Check is working?**

Not yet. You also need the store, authorization, retrieval mechanism, TTL, and recovery policy. A reference does not automatically carry the original data.

**Q17: If a broker republishes the same event at a different offset, should it be treated as a new event?**

Not solely because the offset changed. Determine logical identity from `eventId`/`operationId` and provenance; offset is a transport coordinate.

**Q18: Does upcasting V1 to V2 require changing `eventId`?**

No, if it only changes the representation of the same logical event. A business correction is a different event and needs explicit lineage.

**Q19: Can we conclude business processing succeeded once the envelope is decoded?**

No. Decode, validate, and unwrap are ingress milestones, not proof that external side effects committed.

**Q20: In what order should missing metadata be debugged?**

Check producer/outbox → serialized envelope/wire headers → outbound mapper → broker record → inbound mapper → Spring message → Transformer/Router → domain handler, locating the first point where metadata was dropped or altered.

## 27. Conclusion

**The envelope and the business payload are two distinct layers.** The payload answers **“what happened or needs to be executed in the business domain?”**; the envelope answers **“what is this message, which contract does it belong to, where did it come from, and what are its identity, correlation, and schema?”**. Spring `Message<?>` is a runtime model of payload and headers, while a transport record carries Kafka/JMS/HTTP metadata. They relate to one another, yet **are not automatically equivalent**.

In Spring Integration, a strong **wrap/unwrap** step does more than strip or add a JSON layer. It verifies source/tenant against a trusted context, picks an allowlisted type/version, converts to a typed domain payload, places selected metadata where it belongs, and avoids leaking internal headers or sensitive data. Specifically, **logical event ID differs from Spring `MessageHeaders.ID`; business sequence differs from `schemaVersion`; correlation differs from causation; and a claim reference differs from an operation ID**.

When combining Envelope Wrapper with Router, Filter, Transformer, Splitter, Aggregator, Scatter–Gather, Resequencer, Claim Check, Gateway, retry, and error channels in `SPRING_INTEGRATION_PATTERN`, test **every boundary**: Java objects, Spring Messages, serializers, adapters/transports, business handlers, persistence, and replay. A solid design answers three questions clearly: **“Which payload carries business meaning?”, “Which metadata must travel with it across every hop?”, and “Who is authorized to trust, transform, or consume that metadata?”**

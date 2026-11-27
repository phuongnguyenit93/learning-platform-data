# Envelopes When Messages Traverse Multiple Systems

A message traversing HTTP APIs, Kafka, RabbitMQ, JMS, gateways, or different services carries more than just **business data**. Receivers also commonly need to know *who created the event, what type of event it is, which schema version, when it occurred, which business workflow it relates to, how the data is encoded, and how to trace it*. When that information sits in transport-specific headers, a hop from HTTP to a broker can lose or misinterpret it.

**Envelope Wrapper** is an Enterprise Integration Pattern that packages a **business payload** inside a well-structured **message envelope** carrying metadata allowed across system boundaries. The receiving system validates the envelope, decodes the payload, and turns it into an internal message for processing. When messages traverse multiple systems, distinguish **the original event's identity** from **per-hop forwarding metadata**, and avoid copying headers containing tokens or internal objects to other systems.

The lesson **Envelopes When Messages Traverse Multiple Systems** belongs to the **Envelope wrapper** chapter, module **SPRING_INTEGRATION_PATTERN**. The module teaches implementing Enterprise Integration Patterns with Spring Integration to create loosely coupled, extensible message flows; practicing Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, while testing and observing every processing branch.

**Overarching principle:** *Business data keeps business semantics; envelopes carry the integration contract across boundaries; transport headers remain valid only within their transport scope.* Never assume JSON envelopes, Spring `MessageHeaders`, HTTP headers, and Kafka record headers are the same layer.

## 1. Learning Objectives

After this lesson, you can:

1. Explain Envelope Wrapper and distinguish it from Transformer, Header Enricher, Normalizer, and wire framing.
2. Design an envelope carrying event ID, type, source, version, occurrence time, correlation/causation, and payload.
3. Distinguish business payloads, integration envelopes, Spring Message headers, and transport metadata.
4. Decide which metadata stays stable **end-to-end** versus **per-hop** only.
5. Preserve logical event identity across HTTP → broker → consumer while allowing delivery/message instance IDs to change.
6. Distinguish `eventId`, `messageId`, `correlationId`, `causationId`, `traceId`, `tenantId`, and `schemaVersion`.
7. Attach and validate payload schema/version/content type without arbitrary guessing.
8. Write Java 17 records for domain events/envelopes and wrappers/unwrappers using Jackson.
9. Build Spring Integration Java DSL flows: wrap → outbound channel and inbound → unwrap → business channel.
10. Test round-trips, metadata propagation, content mismatches, unsupported versions, and header leakage.
11. Design adapters across HTTP, Kafka/JMS/AMQP with deliberate metadata mapping rules.
12. Handle retries, DLQs, idempotency, replay, expiry, signatures, and data privacy.
13. Preserve business correlation for Aggregator/Resequencer across hops.
14. Observe every hop without creating high-cardinality metric labels or logging secrets.
15. Establish an evolvable envelope contract when multiple systems run different versions.

## 2. The Problem: One Event Traversing Three Systems

Suppose Order Service emits an `OrderCreated` event, Integration Gateway forwards it to a broker, and Fulfillment Service receives it and saves an order-processing task.

~~~mermaid
flowchart LR
    O["Order Service"] -->|"HTTP / JSON"| G["Integration Gateway"]
    G -->|"Kafka / AMQP"| B[("Message Broker")]
    B -->|"Broker delivery"| F["Fulfillment Service"]
    F --> H["Order Handler"]
~~~

If Order Service sends only:

~~~json
{
  "orderId": "ORDER-101",
  "totalMinorUnits": 250000,
  "currency": "VND"
}
~~~

Fulfillment Service is missing critical context:

- Is this an **OrderCreated** event or an update snapshot?
- Who is the producer for contract verification?
- Has the broker already redelivered this exact event?
- Which tenant does the event belong to?
- Which payload schema version is it?
- Is the timestamp when the business event occurred or when the gateway received it?
- Which ID correlates it with `PaymentCaptured`/`InventoryReserved`?
- On error, how can it be quarantined and replayed?

An explicitly contracted envelope gives all parties shared semantics:

~~~json
{
  "envelopeVersion": "1",
  "eventId": "evt-order-1001",
  "source": "order-service",
  "type": "order.created",
  "schemaVersion": "1",
  "occurredAt": "2026-11-21T02:00:00Z",
  "tenantId": "tenant-a",
  "correlationId": "tenant-a/ORDER-101",
  "causationId": "cmd-place-order-1001",
  "contentType": "application/json",
  "data": {
    "eventId": "evt-order-1001",
    "tenantId": "tenant-a",
    "orderId": "ORDER-101",
    "totalMinorUnits": 250000,
    "currency": "VND",
    "occurredAt": "2026-11-21T02:00:00Z"
  }
}
~~~

This is a **lesson-specific envelope format**, not a claim that all fields above belong to a mandatory standard. In production, teams must agree on field names, JSON Schema/AsyncAPI/OpenAPI, or a chosen event envelope standard such as CloudEvents where appropriate.

### 2.1. What Goes Inside `data`?

`data` holds the **business meaning of `OrderCreated`**, such as order ID, amount, and currency. A consumer can process the business event without knowing whether it arrived via HTTP or Kafka.

### 2.2. What Goes Inside the Envelope?

The wrapper holds metadata needed **between systems**: event ID, source, type, version, original occurrence time, and contracted correlation/causation links. They should not depend on a single broker's header names.

### 2.3. What Belongs in Transport Headers?

HTTP `Authorization`, Kafka partition/offset, JMS delivery mode, RabbitMQ delivery tag, or Spring `replyChannel` serve the current transport/runtime. Never treat them as part of the JSON envelope forwarded to every downstream system.

## 3. Four Layers That Must Not Be Conflated

~~~mermaid
flowchart TB
    T["Transport frame / record
    HTTP / Kafka / JMS / AMQP"]
    E["Integration Envelope
    id / type / source / versions / metadata"]
    D["Business Data
    orderId / amount / currency"]
    S["Spring Message
    payload + internal MessageHeaders"]
    T --> E
    E --> D
    T -.-> S
    E -.-> S
~~~

The diagram is a **conceptual view**: at Java runtime, `Message<ExternalEnvelope>` carries the envelope as its payload; on the wire, a serializer encodes it to bytes and an adapter places those bytes in a transport record.

| Layer | Examples | Responsibility | Lifecycle |
|---|---|---|---|
| Business payload | `OrderCreated` | Domain event semantics | Transport-independent |
| Integration envelope | `eventId, type, source, data` | Inter-system contract | Can span multiple hops |
| Spring `MessageHeaders` | `id, timestamp, replyChannel, errorChannel` | Flow coordination in Spring Integration | Per message/flow instance |
| Transport metadata | HTTP method/headers; Kafka offset; JMS delivery count | Delivery, routing, authentication/ACK | Typically one transport/hop only |

### 3.1. Spring `Message` Already Has Headers—Is an Envelope Still Needed?

Inside one JVM, Spring `Message<T>` suffices to pass payloads and internal metadata. When crossing to HTTP JSON or binary broker records, arbitrary headers can:

- Fail to be transmitted by the serializer.
- Have incompatible names or types at the receiving system.
- Contain `replyChannel` as a non-serializable Java object.
- Be dropped or overwritten by another adapter.
- Expose security-sensitive info across a trust boundary.

An envelope is a **cross-boundary data contract**, not a replacement for all Spring headers. Choose what belongs in the **business/integration contract** versus what is **hop-local**.

### 3.2. Envelopes Differ from Message Encoding/Framing

HTTP/TCP/Kafka each have their own framing or record formats. Envelope Wrapper is a **pattern for exchanged content and metadata**, not a TCP packet or TLS record format. An envelope can be serialized as JSON, Avro, or Protobuf; choosing encoding is a separate contract decision.

## 4. Envelope Wrapper vs. Related EIPs

| Pattern / endpoint | Primary question | Difference from Envelope Wrapper |
|---|---|---|
| **Envelope Wrapper** | How to wrap a payload so external systems understand it? | Creates a shell containing metadata + payload |
| **Transformer** | How to convert payload/message from representation A to B? | Can be used to implement wrap/unwrap |
| **Header Enricher** | How to add metadata to Spring headers? | Does not necessarily create a wire envelope |
| **Normalizer** | How to map multiple source formats to one canonical payload? | May run before/after unwrap depending on boundary |
| **Content-based Router** | Which route should a message take? | Can inspect envelope `type` to route |
| **Filter** | Should the message proceed? | Can reject invalid/unauthorized envelopes |
| **Claim Check** | How to slim payloads with a token instead of large data? | Different from adding a metadata wrapper |
| **Wire Tap** | Copy messages for audit/tracing? | Not responsible for wrapping |
| **Idempotent Receiver** | Avoid duplicate side effects on redelivery? | Can use `eventId` carried by the envelope |
| **Aggregator** | Which group does a message belong to and when is it complete? | Can use business correlation from the envelope |

In Spring Integration, Envelope Wrapper is commonly implemented with `Transformer`, `@Transformer`, Java DSL `.transform(...)`, or adapter serialization. The pattern does not require a built-in Spring Integration class named `EnvelopeWrapper`.

## 5. One Message Across Multiple Hops: What to Keep vs. What Changes?

~~~text
Hop 1: Order Service -> Integration Gateway
Hop 2: Integration Gateway -> Kafka topic
Hop 3: Kafka Consumer -> Fulfillment Service
~~~

| Field | Hop 1 | Hop 2 | Hop 3 | Rule |
|---|---|---|---|---|
| `eventId` | `evt-1001` | `evt-1001` | `evt-1001` | **Keep** when forwarding the same logical event |
| `source` | `order-service` | `order-service` | `order-service` | **Keep** origin; gateway must not impersonate original publisher |
| `type` | `order.created` | `order.created` | `order.created` | Keep unless creating a new event |
| `occurredAt` | `02:00` | `02:00` | `02:00` | Keep original business occurrence time |
| `tenantId` | `tenant-a` | `tenant-a` | `tenant-a` | Keep, yet always verify trust scope |
| `correlationId` | order workflow key | same | same | Keep per domain contract |
| `causationId` | `cmd-1001` | `cmd-1001` | `cmd-1001` | Keep when merely forwarding |
| `schemaVersion` | `1` | `1` | `1` | Keep while `data` schema is unchanged |
| Spring `MessageHeaders.ID` | `UUID-A` | `UUID-B` | `UUID-C` | Can **change** per Message instance |
| HTTP request ID | `req-http-1` | Not equivalent | — | Hop-local |
| Kafka offset | — | `offset-178` | `offset-178` on record receipt | Transport-local; not an event ID |
| Delivery attempt | `1` | `1` | `2` on retry | Changes across redeliveries |
| `receivedAt` | gateway receive time | broker receive time | consumer receive time | Hop-local; never overwrite `occurredAt` |

### 5.1. Forwarding the Same Event vs. Creating a New Event

**Forwarding/republishing the same logical event:** preserve `eventId`, `source`, `type`, and `occurredAt`, while optionally recording hop receipts outside the logical envelope.

**Derived event:** if Fulfillment receives `OrderCreated` and then emits `ShipmentRequested`, that is a **different event**:

~~~text
Input event:
  id=evt-order-1001
  type=order.created

Derived event:
  id=evt-shipment-2001   (new ID)
  type=shipment.requested
  causationId=evt-order-1001
  correlationId=tenant-a/ORDER-101
~~~

Never reuse the same ID for two distinct event types merely because one caused the other. `causationId` captures causality, `correlationId` tracks the workflow, and the new `eventId` identifies the newly emitted event.

### 5.2. Can You Re-Envelope When Changing Schemas?

If an intermediary genuinely **alters meaningful data or the event contract**, define an explicit policy: whether the original event undergoes a representation change while keeping **business event identity** depends on the agreement between parties. A pure format adapter that preserves semantics normally keeps the logical event ID and logs transformation metadata. If creating a **new business event**, issue a new ID and link causation.

## 6. Event ID, Correlation, Causation, and Tracing

Frequently confused IDs:

| Field | Identifies | Should it change across hops? |
|---|---|---|
| `eventId` | One logical event | No when forwarding the same event |
| `correlationId` | Events sharing a workflow | No while workflow is unchanged |
| `causationId` | Event/command that directly led to this event | No when forwarding; updated when emitting a new event |
| `traceId` | One distributed trace | Follows tracing context/propagation |
| `spanId` | One specific span | Usually changes when starting a new span |
| `MessageHeaders.ID` | Spring Message instance | Can change |
| Kafka offset | Record position in partition | Changes per publish location |
| HTTP request ID | One request/attempt | Can change |
| `schemaVersion` | Format/schema of `data` | Changes when payload schema changes per contract |
| `envelopeVersion` | Schema of the envelope itself | Changes when upgrading envelope format |

**Event ID is not Spring Message ID.** Two broker redeliveries may build two different `Message<?>` instances while sharing the same logical `eventId`.

### 6.1. Correlation Must Identify the Right Business Group

If an Aggregator must combine `OrderCreated`, `PaymentCaptured`, and `InventoryReserved` for an order, the group key can be `(tenantId, orderId)`. Never use email, status, timestamp, or an individual part's `eventId` as the group key.

`correlationId` in the envelope must have a contract: is it a workflow ID, request ID, or business group ID? A field name alone does not prove semantics.

### 6.2. Trace Context Does Not Replace Business Correlation

W3C `traceparent` or OpenTelemetry tracing propagates via HTTP and broker headers per instrumentation. One trace can split across async processing; one business workflow can span multiple traces. Never use `traceId` as `orderId` or an idempotency key.

### 6.3. Causation Is Not Send Time

`causationId` answers *which event/command led to this event?* It holds no timestamp and must not be guessed from broker arrival order. When forwarding without creating a new business event, do not overwrite `causationId` with the gateway request ID.

## 7. Envelope Schema Version and Payload Schema Version Differ

The two contracts can upgrade independently:

~~~json
{
  "envelopeVersion": "1",
  "type": "order.created",
  "schemaVersion": "2",
  "data": {
    "orderId": "ORDER-101",
    "amountMinorUnits": 250000
  }
}
~~~

- `envelopeVersion="1"`: field rules and semantics of the wrapper.
- `schemaVersion="2"`: field rules and semantics of `data` for the corresponding event type.
- HTTP API version: can differ from both.
- Application release `4.8.1`: does not necessarily correspond to schema version.

### 7.1. Version Must Pair with Event Type

Schema v1 of `order.created` is not the same as schema v1 of `payment.captured`. Proper schema identifiers typically combine `(source/eventType, schemaVersion)` or a verified schema registry ID.

### 7.2. Do Not Use Version for Business Ordering

An `OrderCreated` v2 and a `PaymentCaptured` v1 can still belong to the same order. Never use `schemaVersion` as `sequenceNumber`, business revision, or a correlation key.

### 7.3. Re-Wrap When Changing `data`

If a Gateway translates payload v1 to canonical v2, it must update `schemaVersion` for the **new payload** and record provenance in a separate field/header if needed. Keeping `schemaVersion=1` alongside v2 `data` causes consumers to pick the wrong decoder.

Do not bump `envelopeVersion` when only `data`'s schema changes. Those are two separate evolution axes.

## 8. Payload, Metadata, and Header Mapping Contract

An envelope traversing multiple systems needs an explicit contract table instead of copying every header:

| Information | Preferred location | Send across boundaries? | Notes |
|---|---|---|---|
| Order ID, amount, currency | `data` | Yes | Business contract |
| Event ID, event type, source | Envelope | Yes | Logical identity |
| Original `occurredAt` | Envelope | Yes | Never overwrite with receive time |
| Schema/envelope versions | Envelope | Yes | Decoder/compatibility |
| Business correlation/causation | Envelope | When needed | Never substitute `traceId` |
| Trace context | Transport headers / tracing metadata | Per policy | W3C/OpenTelemetry context with trust controls |
| Tenant ID | Envelope or authenticated routing context | Conditionally | Always authenticate |
| Authentication bearer token | Hop-local secure header | **Never copy blindly** | Sensitive; may require issuing fresh hop credentials |
| Spring `replyChannel` | Spring Message headers | Never raw across wire | Not an HTTP callback URL |
| Spring `errorChannel` | Spring runtime | Never raw across wire | Only useful in matching runtime context |
| Kafka topic/partition/offset | Transport | Hop-local | Not a business ID |
| Retry attempt/delivery tag | Transport | Hop-local | May reset at new hops |
| Compression/encoding | Wire metadata | Yes if contracted | Enforce size/resource bounds |

### 8.1. Do Not Copy All Spring Headers into a JSON Envelope

An anti-pattern is serializing `message.getHeaders()` into a map inside the envelope. It can contain:

- Non-portable runtime objects like `replyChannel`/`errorChannel`.
- `Authorization`/session metadata.
- Broker-specific headers holding offset, partition, delivery tag.
- Stale `contentType` mismatched with transformed payloads.
- Internal tracking IDs or sensitive data.

**Use an allowlist** for cross-boundary metadata; headers crossing transports must have explicit adapter mappings and trust policies.

## 9. When Do You Not Need a Custom Envelope?

Not every system needs another custom JSON wrapper.

- An API already having an explicit **request/response contract** with tracing and identity may not need extra wrapping.
- A broker already standardized on **CloudEvents** or a schema registry can use that standard rather than inventing one.
- Within a single internal Spring Integration flow, `Message<T>` + headers may suffice.
- When payloads are large files, wrapping all bytes inside JSON inflates memory; consider file metadata, attachments, object storage, or Claim Check per contract.
- When a message already has a standard envelope, **do not nest multiple wrappers** just because it passed another gateway.

The design question is: *which metadata must the receiver understand, across which trust boundaries, and under what compatibility contract?* If an existing standard satisfies those needs, prefer reusing it over inventing a custom envelope.

### 9.1. CloudEvents Is One Option, Not Identical to the Demo

CloudEvents 1.0 defines core attributes like `specversion`, `id`, `source`, `type`, and event data, plus optional attributes like `subject`, `time`, `datacontenttype`, and `dataschema`, along with binding/serialization specifications. The demo JSON `envelopeVersion/eventId/schemaVersion` in this lesson is **not** standard CloudEvents JSON; if adopting CloudEvents, follow the exact field names, types, source/id uniqueness, and structured/binary bindings of the specification—not merely renaming a few properties.

### 9.2. Envelopes Do Not Solve Reliability on Their Own

Wrapping into valid JSON does **not** deliver:

- Exactly-once business side effects.
- Timely broker ACKs.
- Authenticity without security controls.
- Schema compatibility between producers and consumers.
- Accurate correlation if the wrong key is chosen.
- Cross-service transactions.

It merely provides a **contractual frame** so other mechanisms work consistently.

## 10. Test Contract Before Writing Java

Before implementing, lock down the sample contract:

| Item | Example |
|---|---|
| Event type | `order.created` |
| Envelope version | `"1"` |
| Payload schema version | `"1"` |
| Source | `order-service` |
| Event ID | `evt-order-1001`, stable across retries |
| Tenant | `tenant-a`, authenticated at ingress |
| Correlation | `tenant-a/ORDER-101` per business contract |
| Causation | `cmd-place-order-1001` (nullable if absent) |
| Occurrence time | ISO-8601 `Instant` UTC |
| Content type | `application/json` in the example |
| Payload | `OrderCreated` |
| Unknown envelope version | Reject/quarantine; never guess |
| Unknown payload version | Explicit unsupported-schema handling |
| Unknown event type | Route/quarantine; never cast to `OrderCreated` |
| Duplicate event ID | Idempotent Receiver at processing side |
| Security | Verify authenticated source/tenant and enforce size bounds |
| Trace | Propagate per instrumentation/trust policy |
| Replay | Preserve event identity; check dedup ledger retention |

This table is an **application example contract**. Real systems must define owners, version support windows, schema examples, and sensitive-data policies.
## 11. Java 17: Payload and Envelope Models

We build a standalone example for `order.created` using Java 17 and Jackson. Each `public` type below should be saved in **its own Java source file of the same name** when added to a project.

### 11.1. Business Payload Unaware of the Broker

~~~java
public record OrderCreated(
        String eventId,
        String tenantId,
        String orderId,
        long totalMinorUnits,
        String currency,
        String occurredAt
) {}
~~~

`OrderCreated` describes only a business event. There is no Kafka partition/offset, HTTP authorization, or Spring channel address in this record.

In this lesson, money is always in **minor units**; `long` illustrates integer amounts under an explicit currency contract. Never blindly multiply amounts by 100 for every currency or use `double` for currency conversion.

### 11.2. Explicitly Structured Envelope

~~~java
import com.fasterxml.jackson.databind.JsonNode;

public record ExternalEventEnvelope(
        String envelopeVersion,
        String eventId,
        String source,
        String type,
        String schemaVersion,
        String occurredAt,
        String tenantId,
        String correlationId,
        String causationId,
        String contentType,
        JsonNode data
) {}
~~~

Notes:

- `data` is a `JsonNode`, representing a JSON subtree. Other formats may use `byte[]` or a typed union.
- `occurredAt` is an ISO-8601 string; the validator parses it with `Instant.parse`, avoiding timezone-less local times.
- `causationId` may be null if no causing event/command is known.
- `envelopeVersion` versions the **wrapper**; `schemaVersion` versions **`data` per event type**.
- `source` only indicates the declared origin; verify it against an **authenticated** source rather than trusting arbitrary client claims.
- `correlationId` in the example follows a `tenantId/orderId` contract with restricted grammar; do not assume every system uses that format.

### 11.3. Coded Exceptions

~~~java
public final class EnvelopeContractException
        extends RuntimeException {

    private final String code;

    public EnvelopeContractException(String code) {
        super(code);
        this.code = code;
    }

    public EnvelopeContractException(
            String code,
            Throwable cause) {
        super(code, cause);
        this.code = code;
    }

    public String code() {
        return code;
    }
}
~~~

Use stable codes like `ENVELOPE_VERSION_UNSUPPORTED` or `EVENT_ID_MISMATCH` to classify errors; never put full raw payloads or personal data into exception messages.

## 12. Wrapper/Unwrapper: Bidirectional Integration Boundary

We implement `OrderEnvelopeCodec`, taking a Spring `Message<?>` and returning a **new Message** with the transformed payload. Building a new message is intentional so we **do not copy all headers** from external boundaries.

### 12.1. Core Implementation

~~~java
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.regex.Pattern;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class OrderEnvelopeCodec {

    private static final String ENVELOPE_VERSION = "1";
    private static final String SCHEMA_VERSION = "1";
    private static final String EVENT_TYPE = "order.created";
    private static final String EVENT_SOURCE = "order-service";
    private static final String CONTENT_TYPE = "application/json";

    // Intentionally restricted grammar so '/' concatenation stays unambiguous.
    private static final Pattern IDENTIFIER =
            Pattern.compile("[A-Za-z0-9._-]+");

    private final ObjectMapper mapper;

    public OrderEnvelopeCodec(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public Message<ExternalEventEnvelope> wrap(
            Message<?> original) {

        if (!(original.getPayload() instanceof OrderCreated event)) {
            throw new EnvelopeContractException(
                    "OUTBOUND_PAYLOAD_TYPE_INVALID");
        }

        validateOrder(event);

        String causationId =
                optionalStringHeader(original, "causationId");

        ExternalEventEnvelope envelope =
                new ExternalEventEnvelope(
                        ENVELOPE_VERSION,
                        event.eventId(),
                        EVENT_SOURCE,
                        EVENT_TYPE,
                        SCHEMA_VERSION,
                        event.occurredAt(),
                        event.tenantId(),
                        businessCorrelationId(
                                event.tenantId(), event.orderId()),
                        causationId,
                        CONTENT_TYPE,
                        mapper.valueToTree(event));

        MessageBuilder<ExternalEventEnvelope> builder =
                MessageBuilder.withPayload(envelope)
                        .setHeader("eventId", event.eventId());

        copyIfPresent(original, builder, "traceparent");

        return builder.build();
    }

    public Message<OrderCreated> unwrap(
            Message<?> incoming) {

        if (!(incoming.getPayload()
                instanceof ExternalEventEnvelope envelope)) {
            throw new EnvelopeContractException(
                    "INBOUND_ENVELOPE_TYPE_INVALID");
        }

        validateEnvelope(envelope);

        final OrderCreated event;
        try {
            event = mapper.treeToValue(
                    envelope.data(), OrderCreated.class);
        }
        catch (JsonProcessingException e) {
            throw new EnvelopeContractException(
                    "PAYLOAD_DECODE_FAILED", e);
        }

        validateOrder(event);

        if (!envelope.eventId().equals(event.eventId())) {
            throw new EnvelopeContractException(
                    "EVENT_ID_MISMATCH");
        }
        if (!envelope.tenantId().equals(event.tenantId())) {
            throw new EnvelopeContractException(
                    "TENANT_ID_MISMATCH");
        }
        if (!envelope.occurredAt().equals(event.occurredAt())) {
            throw new EnvelopeContractException(
                    "OCCURRED_AT_MISMATCH");
        }

        String expectedCorrelation =
                businessCorrelationId(
                        event.tenantId(), event.orderId());

        if (!expectedCorrelation.equals(
                envelope.correlationId())) {
            throw new EnvelopeContractException(
                    "CORRELATION_ID_MISMATCH");
        }

        MessageBuilder<OrderCreated> builder =
                MessageBuilder.withPayload(event)
                        .setHeader("eventId", envelope.eventId())
                        .setHeader(
                                "businessCorrelationId",
                                envelope.correlationId())
                        .setHeader(
                                "sourceSchemaVersion",
                                envelope.schemaVersion())
                        .setHeader(
                                "sourceSystem",
                                envelope.source());

        copyIfPresent(incoming, builder, "traceparent");

        return builder.build();
    }

    private static void validateEnvelope(
            ExternalEventEnvelope e) {

        requireEqual(
                ENVELOPE_VERSION, e.envelopeVersion(),
                "ENVELOPE_VERSION_UNSUPPORTED");
        requireEqual(
                EVENT_TYPE, e.type(),
                "EVENT_TYPE_UNSUPPORTED");
        requireEqual(
                EVENT_SOURCE, e.source(),
                "EVENT_SOURCE_UNTRUSTED");
        requireEqual(
                SCHEMA_VERSION, e.schemaVersion(),
                "PAYLOAD_SCHEMA_UNSUPPORTED");
        requireEqual(
                CONTENT_TYPE, e.contentType(),
                "CONTENT_TYPE_UNSUPPORTED");

        requireId(e.eventId(), "EVENT_ID_INVALID");
        requireId(e.tenantId(), "TENANT_ID_INVALID");
        requireNonBlank(
                e.correlationId(), "CORRELATION_ID_REQUIRED");
        validateInstant(e.occurredAt());

        if (e.data() == null
                || !e.data().isObject()) {
            throw new EnvelopeContractException(
                    "DATA_OBJECT_REQUIRED");
        }

        if (e.causationId() != null) {
            requireId(
                    e.causationId(), "CAUSATION_ID_INVALID");
        }
    }

    private static void validateOrder(OrderCreated e) {
        requireId(e.eventId(), "EVENT_ID_INVALID");
        requireId(e.tenantId(), "TENANT_ID_INVALID");
        requireId(e.orderId(), "ORDER_ID_INVALID");

        if (e.totalMinorUnits() <= 0) {
            throw new EnvelopeContractException(
                    "AMOUNT_NOT_POSITIVE");
        }

        if (e.currency() == null
                || !e.currency().matches("[A-Z]{3}")) {
            throw new EnvelopeContractException(
                    "CURRENCY_FORMAT_INVALID");
        }

        validateInstant(e.occurredAt());
    }

    private static String businessCorrelationId(
            String tenantId,
            String orderId) {

        requireId(tenantId, "TENANT_ID_INVALID");
        requireId(orderId, "ORDER_ID_INVALID");
        return tenantId + "/" + orderId;
    }

    private static void validateInstant(String value) {
        requireNonBlank(value, "OCCURRED_AT_REQUIRED");
        try {
            Instant.parse(value);
        }
        catch (DateTimeParseException ex) {
            throw new EnvelopeContractException(
                    "OCCURRED_AT_INVALID", ex);
        }
    }

    private static void requireId(
            String value, String code) {

        if (value == null
                || !IDENTIFIER.matcher(value).matches()) {
            throw new EnvelopeContractException(code);
        }
    }

    private static void requireNonBlank(
            String value, String code) {

        if (value == null || value.isBlank()) {
            throw new EnvelopeContractException(code);
        }
    }

    private static void requireEqual(
            String expected,
            String actual,
            String code) {

        if (!expected.equals(actual)) {
            throw new EnvelopeContractException(code);
        }
    }

    private static String optionalStringHeader(
            Message<?> message,
            String name) {

        Object raw = message.getHeaders().get(name);
        if (raw == null) {
            return null;
        }
        if (!(raw instanceof String text)) {
            throw new EnvelopeContractException(
                    "HEADER_TYPE_INVALID");
        }
        return text;
    }

    private static void copyIfPresent(
            Message<?> original,
            MessageBuilder<?> builder,
            String name) {

        Object value = original.getHeaders().get(name);
        if (value != null) {
            builder.setHeader(name, value);
        }
    }
}
~~~

**This example targets a single event type, source, and version**, not an automatic multi-schema parser. Other events need corresponding models/mappers/dispatching. Jackson supports Java records in modern versions (with appropriate project dependencies); `public` types require separate source files.

### 12.2. Differences Between `wrap` and `unwrap`

- `wrap` sets event type/source/schema according to the **authoritative event-emitting adapter**, never reading `source` from an arbitrary user header.
- `unwrap` **validates the envelope first**, then decodes `data` into `OrderCreated`.
- `unwrap` cross-checks `eventId`/`tenantId`/`occurredAt` between the wrapper and `data`, blocking conflicting identities.
- `correlationId` in the example is verified against `tenantId/orderId` because the contract defines it as this business group.
- Both create a **new** Spring Message, forwarding only the selected `traceparent` header after adapter trust checks. Headers like `Authorization`, `replyChannel`, and `errorChannel` never pass through the codec.
- `schemaVersion` is validated before deserializing the matching schema; if v2 exists, use a Normalizer or another version-specific codec rather than casting v2 as v1.
- String-matching `source` **does not authenticate the source**: consumers must verify TLS identity, token claims, signatures, or the equivalent ingress mechanism.
- Three-uppercase-letter `currency` is only a syntactic check; validate against a business currency allowlist and scale rules.

### 12.3. Why Not Copy `occurredAt` into Spring Headers?

The business event already has `occurredAt`, the envelope has the original value, and the decoder cross-checks them. Handlers needing it should read it from the typed payload. Duplicating it into internal headers offers no benefit and risks inconsistency. Flows that genuinely need a routing timestamp header must define a dedicated mapping contract and tests.

### 12.4. Why Validate `data.isObject()`?

When an event payload is expected to be a JSON object, receiving an array, string, or scalar is a contract violation. Do not let Jackson coerce types or silently instantiate empty/default records. For event types that truly have array payloads, declare that in the schema and use the matching validator.

### 12.5. When Tenants Contain Delimiters

The demo intentionally restricts `tenantId`/`orderId` with a regex excluding `/`. If your domain permits arbitrary identifiers, concatenating `tenantId + "/" + orderId` risks collisions. Use a **structured business key** (record/object) or a key codec with length-prefixing/escaping rather than dropping validation and concatenating naively.

## 13. Java DSL: Two Integration Flows for Wrap and Unwrap

We split outbound and inbound into two pipelines. In the demo, `QueueChannel` beans act as **test/observation sinks**; production replaces them with outbound HTTP/Kafka/AMQP adapters and matching inbound consumers.

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
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
public class EnvelopeFlowConfiguration {

    @Bean
    public ObjectMapper envelopeObjectMapper() {
        return new ObjectMapper();
    }

    @Bean
    public OrderEnvelopeCodec orderEnvelopeCodec(
            ObjectMapper envelopeObjectMapper) {
        return new OrderEnvelopeCodec(envelopeObjectMapper);
    }

    @Bean(name = "orders.internal.out")
    public MessageChannel outboundInput() {
        return new DirectChannel();
    }

    @Bean(name = "orders.wire.out")
    public PollableChannel wireOutput() {
        return new QueueChannel();
    }

    @Bean(name = "orders.wire.in")
    public MessageChannel wireInput() {
        return new DirectChannel();
    }

    @Bean(name = "orders.internal.in")
    public PollableChannel inboundOutput() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow envelopeOutboundFlow(
            OrderEnvelopeCodec codec) {

        return IntegrationFlow
                .from("orders.internal.out")
                .transform(codec, "wrap")
                .channel("orders.wire.out")
                .get();
    }

    @Bean
    public IntegrationFlow envelopeInboundFlow(
            OrderEnvelopeCodec codec) {

        return IntegrationFlow
                .from("orders.wire.in")
                .transform(codec, "unwrap")
                .channel("orders.internal.in")
                .get();
    }
}
~~~

Tracing the flow:

~~~text
Internal Order Service
  Message<OrderCreated>
     -> .transform(codec, "wrap")
  Message<ExternalEventEnvelope>
     -> orders.wire.out (test fixture)
     -> Serialize JSON and send over transport (production)

Inbound transport
  JSON bytes -> Decode ExternalEventEnvelope (adapter)
     -> orders.wire.in
     -> .transform(codec, "unwrap")
  Message<OrderCreated>
     -> orders.internal.in (test fixture)
     -> Fulfillment handler (production)
~~~

**Intentionally omitted layer:** the code above does not yet serialize the envelope to `byte[]` on outbound or deserialize `byte[]` on inbound. Those belong to **transport adapters/serializers**. Do not call this demo a complete Kafka integration; it illustrates Spring Integration routing/transform boundaries and enables testing payloads, headers, and metadata.

### 13.1. Sending Over HTTP

A Spring Integration HTTP outbound adapter can send JSON bytes generated from the envelope with `Content-Type: application/json` and hop-specific authentication. HTTP inbound must authenticate, enforce size bounds, parse JSON, validate, and pass the typed envelope into the flow. HTTP `Authorization` must never be copied into `data` or onward broker headers.

### 13.2. Sending Over Kafka or RabbitMQ

Outbound adapters use a serializer for `ExternalEventEnvelope`/JSON bytes. Kafka topic/partition/offset or AMQP delivery tag is **transport metadata**. Inbound adapters decode and pass into wrapper validation; a broker record can be delivered multiple times, so `eventId` inside the envelope must stay stable for Idempotent Receiver.

### 13.3. Request–Reply via a Gateway

A Gateway may have internal `replyChannel`/`errorChannel` headers to match responses. You cannot serialize a Java `replyChannel` object over another broker and expect it to exist in the remote JVM. For cross-system request–reply, define **reply destinations, request/correlation IDs, timeouts, error outcomes, and security** as an explicit protocol (which can use envelopes). When a producer only emits async events, do not carry `replyChannel`.

## 14. Unit Test: Wrapper/Unwrapper and JSON Round-Trip

The tests below exercise the codec **without needing a Spring context**. They prove event identity/correlation survive envelope serialization/deserialization and the original business payload is restored intact.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class OrderEnvelopeCodecTest {

    private final ObjectMapper mapper = new ObjectMapper();
    private final OrderEnvelopeCodec codec =
            new OrderEnvelopeCodec(mapper);

    private OrderCreated sample() {
        return new OrderCreated(
                "evt-order-1001",
                "tenant-a",
                "ORDER-101",
                250000,
                "VND",
                "2026-11-21T02:00:00Z");
    }

    @Test
    void wrapAndUnwrapPreserveLogicalEvent() throws Exception {
        OrderCreated event = sample();

        Message<OrderCreated> internal =
                MessageBuilder.withPayload(event)
                        .setHeader(
                                "causationId",
                                "cmd-place-order-1001")
                        .setHeader(
                                "traceparent",
                                "00-11111111111111111111111111111111"
                                + "-2222222222222222-01")
                        .build();

        Message<ExternalEventEnvelope> wrapped =
                codec.wrap(internal);

        String wireJson = mapper.writeValueAsString(
                wrapped.getPayload());

        ExternalEventEnvelope received =
                mapper.readValue(
                        wireJson, ExternalEventEnvelope.class);

        Message<OrderCreated> unwrapped =
                codec.unwrap(
                        MessageBuilder.withPayload(received)
                                .build());

        assertEquals(
                event, unwrapped.getPayload());

        assertEquals(
                "evt-order-1001",
                received.eventId());
        assertEquals(
                "tenant-a/ORDER-101",
                received.correlationId());
        assertEquals(
                "order-service",
                received.source());
        assertEquals(
                "order.created",
                received.type());
        assertEquals(
                "1",
                received.schemaVersion());
        assertEquals(
                "1",
                received.envelopeVersion());
        assertEquals(
                "cmd-place-order-1001",
                received.causationId());

        assertEquals(
                "evt-order-1001",
                unwrapped.getHeaders().get("eventId"));
        assertEquals(
                "tenant-a/ORDER-101",
                unwrapped.getHeaders()
                        .get("businessCorrelationId"));
    }

    @Test
    void wrapperDoesNotCopySecretInternalHeaders() {
        Message<OrderCreated> input =
                MessageBuilder.withPayload(sample())
                        .setHeader("Authorization", "Bearer SECRET")
                        .setHeader("internalDebug", "do-not-export")
                        .build();

        Message<ExternalEventEnvelope> result =
                codec.wrap(input);

        assertNull(
                result.getHeaders().get("Authorization"));
        assertNull(
                result.getHeaders().get("internalDebug"));

        String envelopeJson =
                result.getPayload().data().toString();
        assertFalse(envelopeJson.contains("SECRET"));
    }

    @Test
    void envelopeEventIdMustEqualPayloadEventId() {
        ExternalEventEnvelope good =
                codec.wrap(
                        MessageBuilder.withPayload(sample())
                                .build())
                        .getPayload();

        ExternalEventEnvelope forged =
                new ExternalEventEnvelope(
                        good.envelopeVersion(),
                        "evt-fake",
                        good.source(),
                        good.type(),
                        good.schemaVersion(),
                        good.occurredAt(),
                        good.tenantId(),
                        good.correlationId(),
                        good.causationId(),
                        good.contentType(),
                        good.data());

        EnvelopeContractException error =
                assertThrows(
                        EnvelopeContractException.class,
                        () -> codec.unwrap(
                                MessageBuilder.withPayload(forged)
                                        .build()));

        assertEquals("EVENT_ID_MISMATCH", error.code());
    }

    @Test
    void unknownEnvelopeVersionIsRejected() {
        ExternalEventEnvelope good =
                codec.wrap(
                        MessageBuilder.withPayload(sample())
                                .build())
                        .getPayload();

        ExternalEventEnvelope unsupported =
                new ExternalEventEnvelope(
                        "99",
                        good.eventId(),
                        good.source(),
                        good.type(),
                        good.schemaVersion(),
                        good.occurredAt(),
                        good.tenantId(),
                        good.correlationId(),
                        good.causationId(),
                        good.contentType(),
                        good.data());

        EnvelopeContractException error =
                assertThrows(
                        EnvelopeContractException.class,
                        () -> codec.unwrap(
                                MessageBuilder
                                        .withPayload(unsupported)
                                        .build()));

        assertEquals(
                "ENVELOPE_VERSION_UNSUPPORTED",
                error.code());
    }
}
~~~

### 14.1. Test JSON, Not Just Object Equality

Two Java DTOs might pass `equals`, yet a serializer could drop fields or rename properties. Testing `writeValueAsString` + `readValue` pushes the entire envelope through JSON representation, catching basic serialization contract bugs.

In real products, add **contract tests using actual producer JSON samples** to verify naming strategies, unknown fields, numeric ranges, version policies, and real serializer settings.

### 14.2. `traceparent` Belongs to the Transport/Tracing Boundary

In the JSON round-trip test above, `traceparent` is in `wrapped`'s Spring header, **not in the JSON envelope**. After serializing only the payload and constructing a new Message, `traceparent` **does not automatically appear**. That is intentional: production adapters/instrumentation must carry W3C tracing context in HTTP/Kafka headers or an explicit envelope policy. Keeping `traceparent` on a local Message never means tracing propagated cross-system.

### 14.3. Test Security at the Right Boundary

Testing that the wrapper omits `Authorization` is necessary yet **not sufficient**: an outbound adapter could still copy headers using a separate mapper. Add transport adapter tests confirming previous-hop credentials never appear in broker/remote logs and each hop configures authentication independently.

## 15. Integration Test Across Spring Integration Channels

This test checks Java DSL wiring without simulating HTTP/Kafka, using `PollableChannel` at both output sinks.

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

@SpringJUnitConfig(classes = EnvelopeFlowConfiguration.class)
class EnvelopeFlowIntegrationTest {

    @Autowired
    @Qualifier("orders.internal.out")
    MessageChannel outboundInput;

    @Autowired
    @Qualifier("orders.wire.out")
    PollableChannel outboundWire;

    @Autowired
    @Qualifier("orders.wire.in")
    MessageChannel inboundWire;

    @Autowired
    @Qualifier("orders.internal.in")
    PollableChannel inboundOutput;

    @Test
    void oneLogicalEventFlowsThroughBothBoundaries() {
        OrderCreated businessEvent = new OrderCreated(
                "evt-order-2001",
                "tenant-a",
                "ORDER-201",
                75000,
                "VND",
                "2026-11-21T02:05:00Z");

        assertTrue(outboundInput.send(
                MessageBuilder.withPayload(businessEvent)
                        .setHeader(
                                "causationId",
                                "cmd-order-2001")
                        .build()));

        Message<?> wrapped =
                outboundWire.receive(1000);

        assertNotNull(wrapped);
        assertInstanceOf(
                ExternalEventEnvelope.class,
                wrapped.getPayload());

        ExternalEventEnvelope envelope =
                (ExternalEventEnvelope) wrapped.getPayload();

        assertEquals(
                "evt-order-2001", envelope.eventId());
        assertEquals(
                "tenant-a/ORDER-201",
                envelope.correlationId());

        assertTrue(inboundWire.send(
                MessageBuilder.withPayload(envelope)
                        .build()));

        Message<?> unwrapped =
                inboundOutput.receive(1000);

        assertNotNull(unwrapped);
        assertEquals(
                businessEvent, unwrapped.getPayload());
        assertEquals(
                "evt-order-2001",
                unwrapped.getHeaders().get("eventId"));
        assertEquals(
                "tenant-a/ORDER-201",
                unwrapped.getHeaders()
                        .get("businessCorrelationId"));

        assertNull(outboundWire.receive(0));
        assertNull(inboundOutput.receive(0));
    }
}
~~~

### 15.1. Explicit Limitations

- Both flows run in the same `ApplicationContext`; wire-adapter JSON serialization is not tested here (unit tests cover JSON round-trip separately).
- `QueueChannel` does not guarantee broker durability/ACKs.
- No real authentication; `source`/`tenantId` must be verified at the ingress adapter.
- No Idempotent Receiver; redelivery can pass the same `eventId` through the flow twice.
- No error routing; an invalid envelope on `DirectChannel` usually raises an exception to the sender, possibly wrapped by Spring.
- Output `MessageHeaders.ID` does not need to match input. Business `eventId` must match.
- When test suites share a cached `ApplicationContext`, drain `QueueChannel`s or isolate contexts to avoid test contamination.

### 15.2. Which Integration Tests Should Be Added?

| Scenario | Expectation |
|---|---|
| Inbound envelope version `"99"` | Reject; never reaches business channel |
| Inbound payload schema version `"99"` | Reject/unsupported path |
| Event type `payment.captured` sent to Order codec | Reject; never cast |
| Envelope `eventId` differs from `data.eventId` | Reject with reason code |
| Envelope `tenantId` differs from `data.tenantId` | Reject |
| Correlation key mismatches order | Reject |
| `data` missing `orderId` | Reject |
| Negative/zero amount outside contract | Reject |
| Invalid ISO timestamp | Reject |
| Unauthorized `source` | Reject, without treating string checks as authentication |
| Transport header contains token | Never leaks across boundary |
| Broker duplicate delivery | Downstream deduplicates by stable `eventId` |
| Inbound serialized JSON exceeds limit | Reject before Jackson parsing |
| Excessively nested JSON | Parser constraint/rejection |
| Schema registry/remote API outage | Bounded retry if transient |

### 15.3. Integration Tests for Invalid Headers Can Walk the Cause Chain

A `DirectChannel` may wrap `EnvelopeContractException` inside `MessageHandlingException`/`MessagingException`. In tests, inspect `Throwable.getCause()` to assert reason codes instead of depending on one specific framework wrapper type.
## 16. HTTP → Broker → Consumer: Per-Hop Handoff Contract

Envelopes crossing multiple systems need explicit **adapter mappings**. A JSON string arriving over HTTP may enter Kafka as a byte-array value alongside dedicated tracing/transport headers.

~~~mermaid
sequenceDiagram
    participant O as Order Service
    participant G as Integration Gateway
    participant K as Kafka/AMQP
    participant C as Fulfillment Consumer

    O->>G: HTTP JSON Envelope + Authorization + traceparent
    G->>G: Authn/Authz + validate envelope/data
    G->>G: Preserve eventId/source/type/occurredAt
    G->>K: JSON bytes + trusted transport headers
    K-->>C: Delivery (redelivery possible)
    C->>C: Decode + verify envelope
    C->>C: Idempotent Receiver by eventId/source/tenant
    C->>C: Business handler
~~~

### 16.1. Hop 1: HTTP Inbound

At the boundary:

1. Authenticate tokens/mTLS or the matching source mechanism.
2. Enforce request size/timeouts, content type, and parser constraints.
3. Decode the envelope per consumer-supported `envelopeVersion`.
4. Check `source`/`tenantId` against the caller's true identity.
5. Cross-check duplicated fields between wrapper and `data`.
6. Reject unsupported event types or payload schemas with reason codes.
7. Only then pass into the normalized internal flow.

A client-supplied `X-Event-Id` HTTP header must be cross-checked against the envelope or ignored as an identity source. **Never create two sources of truth** without a consistency rule.

### 16.2. Hop 2: Sending to Kafka/AMQP

A contract mapper might set:

~~~text
Broker record value:
  UTF-8 JSON bytes of ExternalEventEnvelope

Broker record key:
  partitionKey = trusted tenantId/orderId, if ordering is needed

Broker headers:
  traceparent = tracing propagation per policy
  contentType = application/json
  messageType = order.created, if required by adapter

Broker-provided metadata:
  topic, partition, offset, delivery attempt
~~~

**Partition key** is not `eventId` by default. To keep events for the same order in one partition for per-order ordering, use a canonicalized stable business key; for different load-balancing goals, use a matching contract. Never put secrets or PII into partition keys arbitrarily.

### 16.3. Hop 3: Broker Consumer

Inbound adapter:

- Reads value bytes and decodes the envelope.
- Reads trace context from broker headers per instrumentation.
- Never trusts `source`/`tenant` merely because they appear in JSON; enforce trust models/broker ACLs and validation.
- Uses a stable event key to deduplicate before side effects.
- ACKs/commits offsets per policy only after durable processing.
- Routes non-retryable contract violations to quarantine/DLQ.
- Applies bounded retries for transient errors like DB/network outages.

### 16.4. A Transcoding Hop That Creates No New Business Event

If a Gateway merely converts JSON to Avro or bridges HTTP to Kafka without **changing the logical event**, `eventId`/`source`/`type`/`occurredAt` must not change just because the transport changed. Record hop metadata like `gatewayReceivedAt` in logs/traces or a separate transport header; never overwrite business occurrence time.

## 17. Re-Enveloping vs. Nesting Multiple Envelopes

A gateway sometimes must wrap an event into an **envelope for a different target system**:

~~~text
Original business event
  -> Envelope A (external partner)
  -> Gateway
  -> Envelope B (internal broker contract)
~~~

Two design options exist:

1. **Unwrap A → validate/normalize → wrap B**: suitable when the two contracts differ and the gateway is authorized to translate.
2. **Forward A as an opaque payload inside B**: suitable for store-and-forward or tunneling, yet forces receivers to understand **two layers**.

Do not assume the second option is better merely to decode less. If wrapper B encloses all of wrapper A, receivers must know paths to `eventId`, `contentType`/`schemaVersion` at **both layers**, know when to verify A's signature, and enforce size/nesting limits.

### 17.1. Original Metadata vs. Forwarding Metadata

A message forwarded via a gateway might need both:

~~~text
originSource = order-service
originEventId = evt-order-1001

forwarder = integration-gateway
forwardedAt = 2026-11-21T02:00:05Z
forwardingAttemptId = attempt-3
~~~

Origin identity is **end-to-end**; `forwardingAttemptId` is per-publish metadata that can change on retry. If the envelope contract lacks a `forwarder` field, put it in audit/tracing or transport metadata per policy rather than adding unexpected fields that strict consumers reject.

### 17.2. When Should `source` Change?

If the gateway only forwards the same logical event, preserve the original `source`. If the gateway emits a **new business event** after meaningful processing (e.g., `order.accepted.by.gateway`), it can be the `source` of that new event with a new event ID and causation linking back to the original. Never alter `source` to impersonate another producer.

### 17.3. Avoid Unbounded Envelope Nesting

If each of ten microservices wraps another shell around the message, payload sizes and debugging difficulty soar, risking unbounded nested payloads. Standardize one model separating end-to-end metadata from hop-local headers, with depth limits and explicit unwrap contracts.

## 18. Content-Type, Encoding, Compression, and Parser Protection

A JSON envelope can carry `data` as an object, while other systems pass compressed bytes, binary payloads, or base64.

### 18.1. Which Layer Does `contentType` Belong To?

- HTTP `Content-Type`: media type of the **HTTP request body**.
- Envelope `contentType` in the demo: media type of **`data`**.
- Kafka record serialization: encoding of **record value bytes**.
- Spring `MessageHeaders.CONTENT_TYPE`: internal metadata usable by converters.

They may look identical in simple JSON setups, yet are not always equivalent. For instance, an HTTP body may carry **CloudEvents structured JSON** whose `datacontenttype` describes a different binary payload.

### 18.2. Do Not Trust `contentType` Without Checking Bytes

If a header claims JSON while the body is invalid binary, the decoder must reject rather than endlessly trying every codec. When type/version are incompatible, return an error reason instead of silently falling back to another parser.

### 18.3. Size and Depth Limits

Before parsing external data:

- Enforce request/record size caps per contract.
- Limit JSON nesting depth, field counts, and string lengths.
- Limit decompression ratios to defeat zip bombs.
- Enforce parser timeouts and memory bounds.
- Never log full raw bodies on parse failures.

An envelope wrapper **does not protect against untrusted payloads** without these limits.

## 19. Identity and Idempotent Receiver Across Transports

A broker can redeliver an event after the business handler commits yet before the ACK completes. If the consumer uses `MessageHeaders.ID` or a delivery tag as its idempotency key, retries look like new events.

~~~text
First broker delivery:
  messageId = UUID-A
  eventId   = evt-order-1001
  source    = order-service

Redelivery:
  messageId = UUID-B
  eventId   = evt-order-1001
  source    = order-service
~~~

Use a stable idempotency key, e.g.:

~~~text
(tenantId, source, eventId, eventType)
~~~

or `(source, eventId)` when your event standard guarantees uniqueness within that namespace. Compare payload fingerprints if the same key arrives with different data instead of silently ignoring conflicting events.

### 19.1. Why Not Use `orderId` as the Idempotency Key for Every Event?

An order can have many **distinct business events** (created, paid, shipped, cancelled). Deduplicating solely by `orderId` would block the paid event because created was already processed. Idempotency keys must identify the **exact operation/event to execute at most once**, not just the business entity.

### 19.2. Do Not Mint a New Event ID Inside Unwrap

Anti-pattern:

~~~java
// Wrong: redelivery produces a new idempotency key.
String newEventId = java.util.UUID.randomUUID().toString();
~~~

If an intermediary genuinely creates a new event, record causation. When merely deserializing/forwarding an event, keep the original logical event ID.

### 19.3. Exactly-Once Does Not Come from Envelopes Alone

An envelope carrying `eventId` enables deduplication, yet **does not guarantee exactly-once side effects**. If the marker commits before the business action, a crash loses the task; if the side effect commits before the marker, a retry duplicates it. When markers and business mutations share a DB, use unique constraints in a shared transaction; for remote side effects, use provider idempotency APIs/reconciliation or an inbox/outbox.

## 20. Correlation, Aggregator, and Resequencer Across Systems

Suppose three systems emit three events:

~~~text
Order Service:     OrderCreated(orderId=ORDER-101)
Payment Service:   PaymentCaptured(orderId=ORDER-101)
Inventory Service: InventoryReserved(orderId=ORDER-101)
~~~

Each event has its own `eventId` and `source`. They may use different envelope versions or transport headers, yet must carry a **shared business identity** for an Aggregator to converge them.

~~~mermaid
flowchart LR
    O["Envelope OrderCreated"] --> UO["Unwrap/Normalize"]
    P["Envelope PaymentCaptured"] --> UP["Unwrap/Normalize"]
    I["Envelope InventoryReserved"] --> UI["Unwrap/Normalize"]
    UO --> A[("Aggregator by BusinessKey")]
    UP --> A
    UI --> A
    A --> OUT["OrderReady"]
~~~

### 20.1. Correlation Metadata Needs a Contract

Do not assume every `correlationId` is an order ID. A Payment Service might send a bank transaction's request ID as its `correlationId`. Before the Aggregator, derive a canonical business key `(tenantId, orderId)` and reconcile mappings across external order references.

### 20.2. Sequence Metadata Can Be Hop-Local

`sequenceNumber` and `sequenceSize` are used by Splitter/Resequencer to order parts. Across brokers, carry them in the envelope/headers only when **the batch/sequence contract requires it**. Never substitute `schemaVersion` or `eventId` for sequence numbers.

### 20.3. Different Versions Do Not Split a Group

`OrderCreated` schema v1 and `PaymentCaptured` schema v2 for the same `ORDER-101` still belong in one group. Never use `(orderId, schemaVersion)` as a group key unless the business domain genuinely distinguishes independent workflow runs under a unified run ID.

### 20.4. Filter/Normalizer Before an Aggregator

If a Filter drops a required message while the Aggregator still waits for `sequenceSize=3`, the group stalls; if a Normalizer drops correlation headers, parts scatter into separate groups. Test the entire pipeline end-to-end, not just individual endpoints.

## 21. Security: Authentication, Integrity, and Signatures Across Hops

An envelope can contain `source="order-service"` and `tenantId="tenant-a"`, yet an untrusted client can **write those exact two strings itself**.

### 21.1. Declared Identity Is Not Authenticated Identity

Cross-check:

- Caller identity from mTLS/JWT/broker ACLs.
- Which `source` values the caller is authorized to represent.
- Tenant/subject in the envelope against principals/claims.
- Which event types/schemas the source is authorized to emit.
- Access permissions on resources inside `data`.

Never infer from valid JSON that a message is authorized to trigger side effects.

### 21.2. Signatures Over Raw Wire Representations

To authenticate message **integrity**, protocols may use digital signatures or HMACs. However, a signature is only valid over the **exact canonical representation or bytes that were signed**:

~~~text
Signer signs JSON bytes A.
Gateway parses -> reserializes to JSON bytes B.
Bytes B differ from A (field order / whitespace / encoding).
Signature over A does not necessarily verify B.
~~~

If a gateway must alter representation, it must **verify the old signature first**, then sign the new representation with an authorized identity/key if required by contract—never copy an old signature and pretend it authenticates new bytes.

### 21.3. TLS Protects Hops, Not End-to-End Event Authenticity

TLS/mTLS protects the link between two endpoints on a single hop, while a gateway can read or transform data. If end-to-end origin proof is required, design an end-to-end threat model with signing/auditing. Never assume trace headers or event IDs prove cryptographic integrity.

### 21.4. Do Not Forward Bearer Tokens Across Multiple Systems

An HTTP `Authorization` header from Order Service to Gateway is usually **not** a valid credential for a Kafka Consumer or Fulfillment Service. Use hop-specific authentication/authorization, scoped tokens, or mTLS. Never place bearer tokens inside envelopes, `data`, or logs.

### 21.5. PII and Tenant Isolation

Never put emails, phone numbers, or customer addresses into `eventId` or correlation keys just for debugging convenience. When personal data must travel in `data`, enforce classification, encryption/access controls, retention, and data minimization. On shared brokers, declaring `tenantId` in an envelope never replaces ACLs/authorization.

## 22. Errors, Retries, DLQs, and Replay

Envelope validation can fail at multiple layers:

| Error | Example | Type | Suggested handling |
|---|---|---|---|
| Invalid JSON bytes | Unparseable payload | Deterministic contract | Quarantine/non-retryable |
| Unsupported envelope version | `"99"` | Contract/rollout | Explicit unsupported path |
| Unsupported event type | `payment.captured` into Order codec | Contract/routing | Router/quarantine |
| Unsupported payload schema | Schema v3 lacking converter | Contract/rollout | Quarantine until adapter ships |
| Header/body mismatch | Wrapper `eventId` differs from `data` | Integrity failure | Reject, audit |
| Tenant/source mismatch | Claimed source mismatches principal | Security failure | Deny/audit |
| Invalid timestamp | Not an ISO-8601 `Instant` | Contract | Reject |
| Oversized data | Exceeds ingress cap | Security/contract | Reject before parsing |
| Schema registry unavailable | Cannot resolve schema ID | Transient infra | Bounded retry |
| Broker temporarily unavailable | Publish timeout | Transient/unknown | Retry with stable event ID |
| Remote business API timeout | Commit state unknown | Unknown outcome | Reconcile / idempotent remote |
| Duplicate delivery | Same event ID via broker | Expected transport | Idempotent no-op / return result |

### 22.1. Discard Channel Is Not an Automatic DLQ

In Spring Integration, `discardChannel` normally receives Filter rejections; `errorChannel` receives `ErrorMessage`s from error handling; broker DLQs follow their own policies. Never conflate all three.

An unsupported envelope can enter **quarantine** with reason `UNSUPPORTED_ENVELOPE_VERSION` and safe metadata, then be reprocessed after upgrading the consumer.

### 22.2. Never Retry Deterministic Errors Indefinitely

An event whose wrapper `eventId` disagrees with `data.eventId` will fail identically on every redelivery. Infinite retries spike consumer lag without fixing data. Emit an explicit non-retryable outcome, retain diagnostic info, and avoid dropping data if the contract forbids loss.

### 22.3. Retrying When Publish Outcome Is Unknown

When a gateway publish to a broker times out, the broker may have **already persisted the record** while the response/ACK was lost. If the gateway retries the same logical event, it may write **two broker records**. Receivers need idempotency keyed by stable `eventId`; never mint a fresh event ID per retry.

### 22.4. Reprocessing Days Later

Quarantines/DLQs may contain older envelope versions. When deploying a v2 adapter, do not delete v1 support before replay/retention windows expire. If migrating archived payloads, follow a documented migration and preserve event identity per contract.

## 23. Upgrading Envelopes When Systems Deploy at Different Times

Producers, gateways, and consumers rarely deploy simultaneously. Define a **support matrix** for `envelopeVersion` and payload `schemaVersion`.

| Envelope version | Payload version | Producer | Gateway | Consumer | Outcome |
|---|---|---|---|---|---|
| 1 | 1 | Legacy | Supported | Supported | Accepted |
| 1 | 2 | New producer | Supported | Has v2 normalizer | Accepted after normalize |
| 2 | 2 | New producer | Unaware of wrapper v2 | May support payload | **Gateway rejects** |
| 1 | 99 | Unexpected | Supports wrapper v1 | Unsupported data | Quarantine |
| 99 | 1 | Unexpected | Unsupported wrapper | Cannot decode safely | Reject/quarantine |

### 23.1. Expand Consumers Before Producers Emit New Versions

A rollout sequence:

~~~text
1. Consumers/Gateways support envelopeVersion 1 and 2.
2. Contract tests cover both.
3. Producers enable version 2 canary.
4. Monitor unsupported/mismatch/latency metrics.
5. Stop emitting version 1.
6. Wait out backlogs, DLQs, and archive/replay windows.
7. Retire v1 decoders/transformers per runbook.
~~~

When changing only payload schema v1→v2, you do not have to bump `envelopeVersion`. When changing wrapper semantics or required fields, execute an explicit envelope version migration.

### 23.2. Backward-Compatible Changes Still Need Tests

Adding an optional field to an envelope may be accepted by tolerant readers, yet strict JSON readers reject unknown fields. Renaming `eventId`, changing timestamp types, or removing required fields can be breaking. Never assume “adding a field = guaranteed compatible” without knowing decoder/version policies.

### 23.3. Internal Canonical Contracts Are a Third Axis

A gateway may accept multiple envelope versions and payload schema versions while mapping everything into **one internal canonical business DTO**. That canonical schema can also evolve independently, requiring separate compatibility/migration tests for downstream handlers.

## 24. Multi-Hop Tracing and Logging

A useful trace shows:

~~~text
traceId=trace-1001
  span A: Order Service creates event
  span B: HTTP send to Gateway
  span C: Gateway validates + publishes to broker
  span D: Consumer receives
  span E: Fulfillment business action
~~~

Span IDs change at each step. Business `eventId` remains `evt-order-1001`, linking retries and replays even when one trace ends and a new trace begins.

### 24.1. Standardized Per-Hop Log

~~~text
service=integration-gateway
flow=order-event-forward
eventType=order.created
source=order-service
eventId=evt-order-1001
envelopeVersion=1
schemaVersion=1
outcome=FORWARDED
transport=kafka
attempt=2
traceId=trace-1001
~~~

Control access and retention for `eventId`/tenant logs, optionally using hashing/redaction. Never let message payloads or authentication tokens appear in public logs.

### 24.2. Metric Labels Must Not Hold Raw IDs

| Metric | Purpose | Recommended labels |
|---|---|---|
| `envelope_received_total` | Ingress volume | `source`, `eventType`, `version` |
| `envelope_validated_total` | Contract compliance | `eventType`, `result` |
| `envelope_rejected_total` | Validation/security errors | `reasonCode`, `source` |
| `envelope_forwarded_total` | Forwarded messages | `transport`, `eventType` |
| `envelope_unwrapped_total` | Unwrapped events | `eventType` |
| `envelope_round_trip_latency_seconds` | Latency across hops | `flow`, `transport` |
| `envelope_duplicate_delivery_total` | Redeliveries | `consumer`, `eventType` |
| `envelope_unknown_version_total` | Unsupported versions | `envelopeVersion` |
| `envelope_quarantine_total` | Quarantines | `reason` |
| `envelope_payload_bytes` | Size distribution | `eventType`, `bucket` |

**Never** use `eventId`, `orderId`, `customerId`, `traceId`, or full `correlationId` as high-cardinality metric labels. Those belong in access-controlled logs/traces with retention rules.

### 24.3. Signals of Broken Contracts

- `EVENT_ID_MISMATCH` spikes after a gateway deploy.
- Fulfillment receives envelopes whose `source` differs from peer identity.
- Broker redeliveries mint new event IDs.
- `occurredAt` is replaced by gateway receive time.
- Consumers cannot decode a new version.
- Tracing breaks at the HTTP→Kafka adapter.
- DLQs grow with `CONTENT_TYPE_UNSUPPORTED`.
- Cross-tenant mismatches appear after a tenant routing change.

## 25. Performance, Size, and Backpressure

Envelopes carry overhead: repeated metadata per record, JSON nesting, serialization/deserialization CPU, and occasionally duplicated data in bodies and headers.

### 25.1. Estimating Overhead

A small `OrderCreated` payload may be only a couple hundred bytes; envelope metadata adds source, event type, versions, IDs, and timestamps. Overhead ratio **depends on payload size** and cannot be dismissed as “negligible” automatically. At millions of events per second, hundreds of extra bytes per event affect broker bandwidth and storage.

### 25.2. Do Not Stuff Large Payloads Unchecked into JSON

For large images/files/documents:

- Consider object storage + signed references/Claim Check.
- Put object ID, checksum, `contentType`, and authorization scope in the envelope.
- Enforce authorization and integrity checks when fetching from object storage.
- Manage reference TTLs separately from event retention.
- Never treat signed URLs as safe to log or forward freely.

### 25.3. Backpressure at the Gateway

If the broker slows down, the gateway must not accept HTTP requests and return **business success ACKs** before events are durably persisted per contract. Use transactional outboxes/durable buffers, retries, and backpressure. A valid envelope never proves the broker persisted it.

### 25.4. Avoid N+1 Metadata Lookups

Do not call schema registries, tenant services, or ID-mapping APIs on every single event when caching/contracts allow caching. Caches still need invalidation/version policies, timeouts, and bounded retries; never cache auth decisions indefinitely without controls.

### 25.5. Schema Evolution and Memory

Deserializing full `JsonNode` trees for large payloads consumes substantial RAM. When streaming is needed, use streaming parsers, size bounds, or suitable binary codecs. Never let unknown-version messages pile up unboundedly in in-memory queues.

## 26. Common Anti-Patterns

| Anti-pattern | Consequence | Fix |
|---|---|---|
| Putting all Spring headers into the envelope | Leaks tokens, non-portable objects | Header allowlist |
| Using broker offset as `eventId` | ID changes on republish | Stable logical event ID |
| Minting a new UUID on every forward/retry | Deduplication breaks | Preserve `eventId` when forwarding |
| Gateway overwrites original `source` | Provenance lost | Keep origin; log forwarder separately |
| Overwriting `occurredAt` with `receivedAt` | Wrong business timeline | Separate original vs. hop timestamps |
| Using `traceId` as business correlation | Splits/merges groups wrongly | Stable business key |
| Using `eventId` as Aggregator key across events | Every part lands in its own group | Correlate by order/workflow |
| Using `orderId` alone as idempotency key for all events | Blocks valid follow-up events | Scope by event/operation |
| Using `schemaVersion` instead of business revision | Wrong ordering/state | Separate version axes |
| Keeping old `schemaVersion` after changing payload | Consumers mis-decode | Update payload version |
| Defaulting unknown envelope version to v1 | Silent corruption | Reject/quarantine |
| Treating `source` string as authenticated | Spoofing | Authenticate peer/tenant |
| Copying old signature after reserialization | Invalid integrity check | Verify first, then re-sign |
| Treating hop TLS as end-to-end signature | Gateway can alter bytes | End-to-end threat model |
| Forwarding `Authorization` across brokers | Credential leakage | Per-hop authentication |
| Dropping invalid messages without audit | Hard-to-trace event loss | Quarantine with reason |
| Retrying poison events infinitely | High consumer lag | Non-retryable classification |
| ACKing before persisting | Event loss risk | Commit/ACK policy |
| Thinking envelopes mean exactly-once | Duplicate side effects | Idempotent consumer/outbox |
| Nesting envelopes infinitely across layers | Size/nesting/complexity bloat | Unified contract; bound depth |
| Logging full payloads on parse failures | PII leaks | Redaction/restricted logs |
| Testing objects only, never wire JSON | Serializers drift from contract | Round-trip/contract tests |
| Using `eventId` as a metric label | Cardinality explosion | Bound labels by type/reason |

## 27. Practice Exercises

**Exercise 1 — Contract design.** Starting from a plain `OrderCreated` event, classify payload fields, envelope metadata, and transport-only metadata across HTTP→Kafka.

**Exercise 2 — Wrap/unwrap.** Implement `OrderEnvelopeCodec`; assert round-trips preserve `eventId`/`tenantId`/`orderId`/`amount`.

**Exercise 3 — JSON serialization.** Serialize the envelope to JSON with Jackson and parse it back; compare against producer-provided JSON fixtures.

**Exercise 4 — Header leakage.** Attach `Authorization`, `replyChannel`, and a debug header to a Spring Message; verify the outbound wire message excludes them.

**Exercise 5 — Event ID mismatch.** Alter the envelope `eventId` to differ from `data`'s `eventId`; expect `EVENT_ID_MISMATCH`.

**Exercise 6 — Correlation mismatch.** Change `correlationId` to `tenant-b/ORDER-101`; expect rejection.

**Exercise 7 — Unknown versions.** Send `envelopeVersion` `"99"` and payload `schemaVersion` `"99"`; test both distinct error paths.

**Exercise 8 — Derived event.** From `OrderCreated`, emit `ShipmentRequested`: issue a new event ID, set `causationId` to the old event ID, and keep `correlationId` tied to the order.

**Exercise 9 — Redelivery.** Send the same JSON envelope via two different Spring Message instances; combine with Idempotent Receiver to prevent duplicate side effects.

**Exercise 10 — Replay after migration.** Store a v1 envelope in a DLQ and upgrade the producer to v2; verify the new consumer reads v1 or quarantines per migration policy.

**Exercise 11 — Kafka keys.** Choose a partition key preserving per-order ordering; avoid `eventId` when events for the same order must land on the same partition.

**Exercise 12 — Gateway replies.** Design a request envelope with request ID, reply destination/correlation contract, and timeout; never serialize a `replyChannel` object.

**Exercise 13 — Signatures.** Sign a JSON byte sequence, then alter whitespace; explain why canonicalizing, verifying, and re-signing per protocol are required.

**Exercise 14 — Authentication.** A `tenant-a` client claims `tenant-b` in the envelope; test that the adapter rejects before the business handler.

**Exercise 15 — Large files.** Replace a 20 MB payload with a Claim Check/object storage reference carrying checksum, authorization, and TTL; design failure recovery.

**Exercise 16 — Tracing.** Propagate `traceparent` through a real HTTP→Kafka adapter; assert trace continuation never alters `eventId`.

**Exercise 17 — Observability.** Emit received/validated/forwarded/rejected metrics by event type/version without putting `eventId` in labels.

**Exercise 18 — Batch/aggregation.** Send `OrderCreated`, `PaymentCaptured`, and `InventoryReserved` envelopes from three sources; normalize and group by trusted `tenantId`/`orderId`.

### Minimum Test Matrix

| Input | Expected outcome |
|---|---|
| Valid v1 envelope | Unwraps cleanly to `OrderCreated` |
| Wrap then JSON round-trip | Payload preserved intact |
| Same logical event, redelivery | Event ID unchanged |
| Different Spring Message IDs | Does not create a different business event ID |
| Envelope `eventId` differs from `data` | Reject |
| Envelope tenant differs from `data` | Reject |
| Invalid `correlationId` | Reject |
| Unknown `envelopeVersion` | Unsupported contract error |
| Unknown `schemaVersion` | Unsupported payload schema |
| Wrong event type/source | Reject/dedicated routing |
| Missing `orderId` | Validation rejection |
| Invalid amount | Reject; never auto-correct |
| Invalid ISO-8601 timestamp | Reject |
| `Authorization` in headers | Never emitted on the wire |
| Tenant mismatches authenticated identity | Security rejection |
| Oversized/deeply nested JSON | Ingress rejects before parsing |
| HTTP→broker adapter | Preserves event identity/trace per contract |
| Broker redelivery | Idempotent side effect |
| Archived v1 envelope | Covered by replay/migration policy |
| Registry/backend outage | Bounded retry; never silently drop |

### Self-Check Questions

1. What does Envelope Wrapper add compared to a business payload?
2. Why can Spring `MessageHeaders` not replace every cross-system envelope?
3. Which metadata should stay unchanged end-to-end when merely forwarding?
4. When must a new event ID be minted?
5. How does `causationId` differ from `correlationId`?
6. Is `traceId` a business correlation key?
7. How do source, schema, and envelope versions differ?
8. Can a broker offset serve as `eventId`?
9. Should HTTP `Authorization` live inside a JSON envelope?
10. Why must `eventId` be cross-checked between wrapper and `data`?
11. Why is a `source` string insufficient to authenticate a publisher?
12. What bugs arise from keeping an old schema version alongside newer `data`?
13. When is a Normalizer needed after unwrapping?
14. Does a standardized envelope guarantee exactly-once processing?
15. Why can JSON reserialization invalidate a signature?
16. How do discard/error channels differ from DLQs?
17. Can a Gateway's `replyChannel` be sent as a Java object over a broker?
18. What should happen on an unknown `envelopeVersion`?
19. Why keep v1 adapters after producers switch to v2?
20. Which tests catch header leakage?
21. When should you prefer CloudEvents over a custom envelope?
22. Why avoid nesting envelopes indefinitely?
23. When should you use Claim Check instead of embedding files inside envelopes?
24. Which envelope metadata poses high-cardinality risks?
25. How do you preserve Aggregator correlation when producers use different transports?

## 28. Multi-System Envelope Wrapper Checklist

- Explicit contracts exist for business `data` and integration envelopes.
- Spring headers are never confused with wire envelopes or transport headers.
- Event type, source, `eventId`, and versions have defined schemas and owners.
- Event IDs remain stable when forwarding/retrying the same logical event.
- New events receive new IDs and causation links when appropriate.
- `correlationId` has published business semantics.
- `occurredAt` is never overwritten by receive/publish timestamps.
- `schemaVersion` describes the current payload; `envelopeVersion` describes the wrapper.
- Missing/unknown versions follow explicit reject/quarantine policies.
- Inbound validates `eventId`, tenant, source, type, version, and `contentType`.
- Duplicated fields in envelope and `data` are cross-checked.
- Cross-boundary headers use an allowlist.
- `Authorization`, internal channel objects, and secret tokens are never forwarded.
- Trace context is propagated properly by instrumentation/adapters.
- Tenant/source are authenticated and authorized at ingress.
- Signatures are verified over the exact signed representation; re-signed after transforms if needed.
- JSON parsers enforce size, depth, and time limits plus schema validation.
- Units are never guessed or converted implicitly, nor are uncontracted business defaults invented.
- Broker publishing/ACKs follow a durability policy.
- Idempotent Receiver uses stable keys and accurate fingerprints.
- Transient errors retry with backoff/max attempts; deterministic errors do not loop.
- Quarantines/DLQs define reason codes, retention, and replay plans.
- Gateway request–reply defines clear response and correlation protocols.
- Aggregators correlate by business identity, never `schemaVersion` or `eventId`.
- Wire JSON/serializer contract tests run against producer fixtures.
- Unit tests cover wrap/unwrap, mismatches, and unknown versions.
- Integration tests cover Spring channels and real broker/HTTP adapters where needed.
- Canary/expand-migrate-contract plans account for archived v1 events.
- Metrics slice by type/version/outcome without raw IDs in labels.
- Payload size limits, backpressure, and large-file strategies are in place.
- Runbooks cover replay, rollback, key rotation, and schema migration.

## 29. Summary

**Envelopes when messages traverse multiple systems** package **business payloads** and **integration metadata** into a contract understandable across HTTP, brokers, and diverse runtimes. The wrapper tells receivers what kind of event arrived, who claims to have emitted it, which event ID must stay stable, which schema/version to decode, when the business event originally occurred, and which workflow it belongs to. Nevertheless, it **does not replace** authentication, schema validation, idempotency, retry/ACK policies, or transactions.

In Spring Integration, Envelope Wrapper can be implemented with **wrap/unwrap Transformers** on `Message<?>` and composed with Router, Header Enricher, Normalizer, Filter, Gateway, Aggregator, and error channels. Across multiple hops, separate **logical event IDs** from **message/delivery IDs**, **correlation/causation** from **tracing**, **payload schema version** from **envelope version**, and **end-to-end metadata** from **hop-local headers**.

A strong design combines **header allowlists, version support matrices, explicit unsupported paths, canonical identities, authenticated sources/tenants, bounded parsing, and deduplication**. Testing must cover wire round-trips, Spring integration channels, and real-world scenarios like redelivery, missing fields, wrong tenants, legacy replay, and signatures after reserialization. Once these boundaries are clearly defined, **`SPRING_INTEGRATION_PATTERN`** flows scale smoothly across systems without losing message identity, meaning, or traceability.

### References

- Enterprise Integration Patterns — Envelope Wrapper: https://www.enterpriseintegrationpatterns.com/patterns/messaging/EnvelopeWrapper.html
- Enterprise Integration Patterns — Message Translator: https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessageTranslator.html
- Enterprise Integration Patterns — Correlation Identifier: https://www.enterpriseintegrationpatterns.com/patterns/messaging/CorrelationIdentifier.html
- Enterprise Integration Patterns — Idempotent Receiver: https://www.enterpriseintegrationpatterns.com/patterns/messaging/IdempotentReceiver.html
- CloudEvents Specification 1.0: https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md
- W3C Trace Context: https://www.w3.org/TR/trace-context/
- Spring Integration Reference — Message: https://docs.spring.io/spring-integration/reference/message.html
- Spring Integration Reference — Message Transformation: https://docs.spring.io/spring-integration/reference/transformer.html
- Spring Integration Reference — Message Routing: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration Reference — HTTP Support: https://docs.spring.io/spring-integration/reference/http.html
- Spring Integration Reference — Error Handling: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference — Aggregator: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference — Claim Check: https://docs.spring.io/spring-integration/reference/claim-check.html
- Jackson Databind README: https://github.com/FasterXML/jackson-databind
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/

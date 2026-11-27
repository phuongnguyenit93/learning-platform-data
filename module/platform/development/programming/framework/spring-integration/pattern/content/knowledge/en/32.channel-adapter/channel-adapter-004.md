# Adapter for payload and header conversion

## 1. The problem: the same event is represented differently by each system

In the **SPRING_INTEGRATION_PATTERN** module, we learn how to implement **Enterprise Integration Patterns (EIP)** with **Spring Integration** to build loosely coupled, extensible, and observable messaging flows. When Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation work together, a common issue appears right at the system boundary: **the message format of the outside world matches neither a Spring Message nor the application's domain objects**.

For example, a partner sends an order event over HTTP or JMS:

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-order-901",
  "orderId": "ORD-901",
  "sku": "SKU-RED",
  "quantity": 2,
  "workflowEpoch": 3
}
~~~

The partner may also attach:

~~~text
HTTP header: X-Event-Id: evt-order-901
HTTP header: X-Tenant-Id: tenant-admin
HTTP header: Content-Type: application/json

JMS property: event_id = evt-order-901
JMS property: partner_schema_version = 1
JMS header: JMSMessageID = ID:...
~~~

Inside Spring Integration, an internal handler might require a **Message<OrderCommand>** with standardized headers:

~~~text
Message.payload:
  OrderCommand(orderId=ORD-901, sku=SKU-RED, quantity=2, epoch=3)

Message.headers:
  trustedTenantId = tenant-a
  businessEventId = evt-order-901
  producerId = partner-a
  businessCorrelationKey = order:tenant-a:ORD-901:epoch-3
~~~

A **Channel Adapter** is the bridge that moves data **into** or **out of** the messaging system. The hard part is not just reading from HTTP/JMS/files or writing to a broker; it is also **payload conversion, header mapping, context verification, error management, and preserving identity across the transport boundary**.

### Lesson objectives

After this lesson, you will be able to:

1. Distinguish **Channel Adapter**, **Messaging Gateway**, **Message Translator/Transformer**, **MessageConverter**, and **HeaderMapper**.
2. Trace the path of payloads and headers through inbound and outbound adapters.
3. Design a **wire DTO → typed domain payload → wire DTO** contract with versioning and validation.
4. Convert transport headers into Spring MessageHeaders via an **allowlist**, without turning client claims into trusted data.
5. Understand the difference between business identity and technical headers of HTTP/JMS/AMQP/Spring Integration.
6. Build a Java 17 + Spring Integration example illustrating inbound/outbound boundaries and testing realistically across Spring channels.
7. Handle invalid schemas, missing/wrong-typed headers, duplicates, replies/errors/timeouts, and safe retries.
8. Know how to test and observe an adapter when it drops payloads or correlation metadata.

## 2. What role does a Channel Adapter play in Enterprise Integration Patterns?

A **Channel Adapter** connects an application, data source, or protocol to a **Message Channel**. An inbound adapter takes data from outside and **emits a Message onto a channel**; an outbound adapter **receives a Message from a channel** and sends its contents to an external system.

~~~mermaid
flowchart LR
    X["External system / file / broker"] --> I["Inbound Channel Adapter"]
    I --> C["Spring MessageChannel"]
    C --> R["Router / Transformer / Service Activator"]
    R --> O["Outbound Channel Adapter"]
    O --> Y["External system / file / broker"]
~~~

| Component | Primary responsibility | What it does not guarantee by itself |
| --- | --- | --- |
| **Inbound Channel Adapter** | Receive/poll external data, create a Spring Message | That the payload is business-valid or the tenant is authorized |
| **Outbound Channel Adapter** | Receive a Spring Message and send it to an external system | That the remote side completed business logic or replied |
| **MessageConverter** | Convert bytes/text/objects according to the wire format | Authorization or correct correlation |
| **HeaderMapper** | Map selected transport properties and Spring headers | That headers came from a trusted source |
| **Transformer/Translator** | Convert internal representations or normalize payload/headers | Transactions spanning multiple services |
| **Messaging Gateway** | Provide request/reply invocation with a return value | Exactly-once remote effects |
| **Filter/Router** | Pass/drop or select a branch based on a Message | That incoming data is inherently trustworthy |

An outbound Channel Adapter typically carries **one-way send** semantics; if the caller needs a response tied to a request, use an **outbound Gateway/request-reply adapter** rather than treating a successful send as business completion.

### 2.1. Inbound and outbound are opposite directions

~~~text
Inbound:
  transport bytes + native metadata
      -> deserialize payload
      -> validate source and schema
      -> map/construct Spring headers
      -> Spring Message<T>

Outbound:
  Spring Message<T>
      -> validate outgoing contract
      -> serialize permitted wire payload
      -> map selected Spring headers to native metadata
      -> send bytes/properties
~~~

The two directions can be **asymmetric**: an inbound adapter may receive many native headers while selecting only two into the internal Message; an outbound adapter may emit a different set of headers per partner contract. Never assume a received header will automatically be echoed back.

### 2.2. How does an Adapter differ from a Transformer?

A Transformer can convert **OrderWireV1 → OrderCommand** inside Spring Integration, whereas an adapter also handles **protocol and send/receive lifecycle**: connections, polling, ACKs, converters, native properties, error handling, and backpressure. In a real flow, you typically combine **adapter + transformer** rather than packing all logic into one large endpoint.

### 2.3. How does an Adapter differ from a Gateway?

~~~text
Adapter:
  external event -> channel
  channel -> external destination

Gateway:
  request -> channel/transport -> correlated reply
  caller waits for or receives a result
~~~

For an inbound HTTP request needing a synchronous HTTP response, an **inbound HTTP Gateway** is usually more suitable than a one-way inbound Channel Adapter. For reading files, consuming event streams, or writing audits to a broker, adapters are the natural choice.

## 3. Distinguishing three representation layers

Many production bugs happen because teams use the single word "header" for three distinct kinds of information:

~~~mermaid
flowchart TD
    W["Wire message: bytes + native headers"] --> A["Adapter / Converter / HeaderMapper"]
    A --> M["Spring Message: typed payload + MessageHeaders"]
    M --> D["Domain service: DTO + trusted business context"]
~~~

| Layer | Payload | Header/context |
| --- | --- | --- |
| **Wire** | JSON/XML/text/byte array/file | HTTP headers, JMS properties, AMQP properties, file metadata |
| **Spring Messaging** | Java object or bytes inside Message | Immutable MessageHeaders, id/timestamp, replyChannel/errorChannel, custom headers |
| **Domain** | OrderCommand, OrderAccepted, Money... | VerifiedTenant, businessEventId, workflow identity in typed context |

**Spring MessageHeaders are not identical to HTTP headers.** HTTP `X-Event-Id` becomes Spring `businessEventId` only if the adapter/mapper creates that mapping. After crossing another broker, it can be renamed, mistyped, or lost without an explicit wire contract.

### 3.1. A naming-mismatch example

~~~text
Wire HTTP:
  X-Event-Id = evt-order-901

Spring Message:
  x_event_id = evt-order-901

Downstream:
  @Header("businessEventId") String eventId
~~~

The handler may miss a required header because the three names are **not equivalent**. Standardize mappings at the boundary rather than letting each business handler guess partner-specific names.

### 3.2. Payload conversion and header conversion are two separate problems

- **Payload conversion:** JSON bytes to OrderWireV1 and then to OrderCommand; converting encoding, schema version, enums, and business fields.
- **Header conversion:** native property `event_id` or HTTP `X-Event-Id` into a stable Spring header; cross-checking against payload eventId when required.
- **Context binding:** attaching `trustedTenantId` from authentication/authorization rather than taking self-asserted values from HTTP.

Do not collapse all three steps into a `copyHeaders(raw)` and consider conversion finished.

## 4. Inbound adapter: a reliable processing sequence

An inbound adapter should perform its work in order:

1. Receive from the configured source (poll file, read broker, accept HTTP callback, etc.).
2. Enforce message size limits and verify encoding/content type and schema.
3. Authenticate the producer via credentials, mTLS, signature, or broker ACL.
4. Deserialize the payload and validate fields/enums/units.
5. Authorize the producer for the stated tenant/entity/workflow.
6. Verify eventId and correlation against the published contract.
7. Build a **trusted Spring Message** with allowlisted headers.
8. Send into the internal channel for Router, Filter, Transformer, and Service Activator processing.
9. ACK/commit according to the inbound adapter's semantics and transaction/recovery policy.

Not every transport performs every step in the same class; what matters is **never letting untrusted metadata become a trusted application header before verification steps run**.

### 4.1. Avoid confusing ACK with business outcome

With a broker, an ACK may mean the consumer received or processed up to a specific boundary. With HTTP, a 200/202 response may come from the adapter itself. Do not infer that downstream finished ledger posting, called a provider, or emitted an event unless the contract specifies so.

### 4.2. Distinguish receive timestamp from event time

HTTP/JMS broker timestamps, MessageHeaders.TIMESTAMP, and a business event's `occurredAt` field can differ. When measuring latency, keep clear which timestamp was generated by the producer, which was verified/recorded by ingress, and which was created by Spring Message.

### 4.3. Inbound can be a poller

When reading files or queues, a `poller` determines fetch cadence, maxMessagesPerPoll, and error handling. When consumers fall behind, you need bounded capacity/backpressure; do not merely increase polling intervals to mask an unmonitored queue backlog.

## 5. Outbound adapter: export only what the wire contract allows

The outbound direction is not "serialize the entire Message object." An outbound adapter must:

1. Determine the target transport/destination from trusted configuration or a business routing allowlist.
2. Select the proper schema version for the receiver.
3. Convert the typed payload into a wire DTO and bytes.
4. Construct native headers/properties from **allowlisted metadata**.
5. Strip live Spring runtime headers such as `replyChannel`, `errorChannel`, and internal channel references.
6. Send and record the transport send result per the adapter's semantics.
7. Handle retries, DLQ/outbox/recovery if sending fails or the outcome is uncertain.

### 5.1. Risk of accidentally serializing control headers

A Spring Message may contain `replyChannel` holding a **MessageChannel object** created by a Gateway. That header is not a portable JSON/broker property and can leak topology. Likewise, errorChannel/routingSlip are not values for an external producer to dictate.

### 5.2. Why not echo all headers?

An inbound request may carry Authorization, cookies, broker delivery tags, partner request IDs, source IP, and runtime metadata. An outbound reply/event should send only **fields permitted by the contract**. Retaining internal message context for tracing does not mean broadcasting the entire context to partners.

### 5.3. One-way means no business reply

When an outbound adapter publishes an event to a broker, the sender may receive a broker confirmation without receiving `OrderAccepted` from a business consumer. If a business reply is needed, design an **outbound Gateway** or a completion event/status API with explicit correlation and timeout.

## 6. Sample contract for converting an order event

We will build an **in-memory adapter harness** so we can test mapping without deploying an HTTP server or broker. The harness simulates both boundaries:

- **Inbound:** a data frame received from the transport containing JSON, native headers, and a verified producer context.
- **Outbound:** a processed event serialized to JSON alongside an allowlisted set of native headers.

This is a **harness simulating adapter responsibilities**, not production HTTP/JMS/AMQP connection code. In real integration, the receive/send ends are swapped for actual adapters while business DTOs, mappers, validation, and tests remain reusable.

### 6.1. Wire request v1

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-order-901",
  "orderId": "ORD-901",
  "sku": "SKU-RED",
  "quantity": 2,
  "workflowEpoch": 3
}
~~~

Two illustrative native headers:

~~~text
x-event-id: evt-order-901
content-type: application/json
~~~

These are merely **source-supplied metadata**. If raw eventId appears in both body and header, the mapper must verify consistency and then bind that identity to the authenticated source/tenant and replay-protection policy.

### 6.2. Internal message contract

~~~text
Message.payload = OrderCommand(
    orderId="ORD-901",
    sku="SKU-RED",
    quantity=2,
    workflowEpoch=3
)

Message.headers:
    trustedTenantId="tenant-a"
    producerId="partner-a"
    businessEventId="evt-order-901"
    businessCorrelationKey="order:tenant-a:ORD-901:epoch-3"
~~~

**trustedTenantId** must come from the authenticated producer + authorization registry. Never use a client-provided x-tenant-id to construct trustedTenantId.

### 6.3. Wire output v1

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-order-901",
  "orderId": "ORD-901",
  "outcome": "ACCEPTED"
}
~~~

Outbound headers:

~~~text
content-type: application/json
x-event-id: evt-order-901
x-schema-version: 1
~~~

**ACCEPTED** in the harness means recorded by the in-memory processor, **not a guarantee that an order was durably committed or shipped**. In production, you must define precisely how far persistence has progressed when ACK/ACCEPTED is emitted.

## 7. Typed wire DTOs and domain payloads

Using Java 17 records with validation catches schema errors early.

~~~java
import java.util.Objects;

record OrderWireV1(
        int schemaVersion,
        String eventId,
        String orderId,
        String sku,
        int quantity,
        int workflowEpoch) {

    OrderWireV1 {
        if (schemaVersion != 1) {
            throw new IllegalArgumentException(
                    "UNSUPPORTED_SCHEMA_VERSION");
        }
        if (eventId == null
                || !eventId.matches("[A-Za-z0-9_-]{1,96}")) {
            throw new IllegalArgumentException("INVALID_EVENT_ID");
        }
        if (orderId == null
                || !orderId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("INVALID_ORDER_ID");
        }
        if (sku == null
                || !sku.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("INVALID_SKU");
        }
        if (quantity < 1 || quantity > 1000) {
            throw new IllegalArgumentException("INVALID_QUANTITY");
        }
        if (workflowEpoch < 1) {
            throw new IllegalArgumentException("INVALID_WORKFLOW_EPOCH");
        }
    }
}

record OrderCommand(
        String orderId,
        String sku,
        int quantity,
        int workflowEpoch) {

    OrderCommand {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(sku, "sku");
        if (quantity < 1 || workflowEpoch < 1) {
            throw new IllegalArgumentException("INVALID_ORDER_COMMAND");
        }
    }
}

record OrderAccepted(
        String tenantId,
        String producerId,
        String eventId,
        String orderId,
        String outcome) {
}

record OrderAckWireV1(
        int schemaVersion,
        String eventId,
        String orderId,
        String outcome) {
}
~~~

**OrderWireV1** is the schema at the transport boundary. **OrderCommand** is the internal payload. **OrderAccepted** represents the simulated processor result. **OrderAckWireV1** is the outbound DTO allowed to leave the system; it intentionally **omits tenantId, principal, and framework replyChannel**.

### 7.1. Why not serialize OrderAccepted directly?

A domain object can evolve for internal requirements, such as adding internalRiskScore, auditOwner, or tenant authorization data. If the outbound adapter serializes that entire record, internal fields can leak into the external contract. A wire DTO **deliberately selects** which fields the receiver may see.

### 7.2. Do not assume ObjectMapper alone is a security boundary

ObjectMapper converts JSON to Java objects; it **does not verify producer identity or tenant ownership**. On untrusted input, constrain payload size, nesting depth, unknown fields, and allowed enum values, and never enable arbitrary polymorphic deserialization driven by client-supplied class names.

### 7.3. Wire schemas may differ in types from domain schemas

A partner may send timestamps as ISO-8601 Strings while the domain uses Instant. A price may be in minor units (long) or a decimal string with Currency. The converter must define **units, timezone, precision, and null semantics**, not just rename fields.

## 8. Verified producer context and inbound frame

An adapter must separate **self-declared wire metadata** from **identity produced by authentication**.

~~~java
import java.util.Map;
import java.util.Objects;

record VerifiedProducer(
        String tenantId,
        String producerId) {

    VerifiedProducer {
        if (tenantId == null
                || !tenantId.matches("[a-z0-9_-]{1,48}")) {
            throw new IllegalArgumentException("INVALID_TENANT_ID");
        }
        if (producerId == null
                || !producerId.matches("[a-z0-9_-]{1,48}")) {
            throw new IllegalArgumentException("INVALID_PRODUCER_ID");
        }
    }
}

record TransportFrame(
        String jsonBody,
        Map<String, String> nativeHeaders,
        VerifiedProducer producer) {

    TransportFrame {
        Objects.requireNonNull(jsonBody, "jsonBody");
        nativeHeaders = Map.copyOf(nativeHeaders);
        Objects.requireNonNull(producer, "producer");
    }
}

interface OrderSourceAuthorization {
    void assertMayPublish(
            VerifiedProducer producer,
            OrderWireV1 event);
}
~~~

**VerifiedProducer is just a Java record representing an authentication outcome**, not an authentication mechanism itself. In production code, the transport adapter/ingress must actually verify mTLS/JWT/broker ACL/signatures and bind tenant and producerId against an authoritative registry.

### 8.1. Never let clients construct VerifiedProducer

Wrong:

~~~java
// Do not use as production ingress.
VerifiedProducer untrusted = new VerifiedProducer(
        httpRequest.getHeader("X-Tenant-Id"),
        httpRequest.getHeader("X-Producer-Id"));
~~~

Right order of responsibilities:

~~~text
HTTP/JMS/AMQP credentials
    -> authenticate producer
    -> authorize producer for tenant + order
    -> VerifiedProducer
    -> TransportFrame
    -> inbound mapper
~~~

### 8.2. The frame holds raw native headers, but the internal Message does not

TransportFrame in the harness carries a nativeHeaders Map for testing. However, **only the mapper may read this Map**. Internal business handlers must not receive the full nativeHeaders map or know about x-tenant-id, JMSCorrelationID, broker delivery tags, or HTTP cookies.

### 8.3. Idempotency rules in the example

An eventId may be unique only within a producer's namespace. Therefore, the harness deduplication scope is **tenantId + producerId + eventId**. The same key with a different payload is a conflict. In production, a concrete contract is needed to specify whether eventId is globally unique or source-scoped.

## 9. Inbound mapper: JSON + headers to trusted Spring Message

This is where the three steps—**decode**, **verify**, and **build internal Message**—are separated.

~~~java
import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class OrderInboundMapper {
    private static final int MAX_WIRE_BYTES = 64 * 1024;

    private final ObjectMapper objectMapper;
    private final OrderSourceAuthorization authorization;

    OrderInboundMapper(
            ObjectMapper objectMapper,
            OrderSourceAuthorization authorization) {
        this.objectMapper = objectMapper;
        this.authorization = authorization;
    }

    Message<OrderCommand> toTrustedMessage(TransportFrame frame) {
        int bytes = frame.jsonBody()
                .getBytes(StandardCharsets.UTF_8).length;
        if (bytes == 0 || bytes > MAX_WIRE_BYTES) {
            throw new IllegalArgumentException(
                    "WIRE_PAYLOAD_SIZE_INVALID");
        }

        OrderWireV1 wire;
        try {
            wire = objectMapper.readValue(
                    frame.jsonBody(), OrderWireV1.class);
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException(
                    "INVALID_ORDER_WIRE_JSON", ex);
        }

        String declaredEventId = frame.nativeHeaders()
                .get("x-event-id");
        if (declaredEventId != null
                && !declaredEventId.equals(wire.eventId())) {
            throw new SecurityException(
                    "EVENT_ID_HEADER_PAYLOAD_MISMATCH");
        }

        // Must bind producer/tenant before business processing.
        authorization.assertMayPublish(frame.producer(), wire);

        OrderCommand command = new OrderCommand(
                wire.orderId(),
                wire.sku(),
                wire.quantity(),
                wire.workflowEpoch());

        String correlation = "order:"
                + frame.producer().tenantId() + ":"
                + wire.orderId() + ":epoch-"
                + wire.workflowEpoch();

        return MessageBuilder.withPayload(command)
                .setHeader("trustedTenantId",
                        frame.producer().tenantId())
                .setHeader("producerId",
                        frame.producer().producerId())
                .setHeader("businessEventId", wire.eventId())
                .setHeader("businessCorrelationKey",
                        correlation)
                .build();
    }
}
~~~

**Key design point:** there is no `copyHeaders(frame.nativeHeaders())`. A transport sender might attempt to inject `replyChannel` or `trustedTenantId` into the Map. The internal Spring Message is constructed solely with application-owned headers.

### 9.1. Event ID in body and header

The example allows `x-event-id` to be absent if `eventId` is already present in the body, while requiring an exact match whenever the header is supplied. Another contract might require `x-event-id` to always be present; adjust validation accordingly. Never arbitrarily pick one of the two values on a mismatch.

### 9.2. Why not use the request IP as the tenant?

Source IP or broker connection name can be useful for auditing, but neither is sufficient to identify who is authorized for an order. The producer must be authenticated and authorized against a registry/business policy.

### 9.3. When JSON is invalid

Jackson may throw parse or mapping errors; record constructors may throw IllegalArgumentException from schema validation. The adapter must distinguish input errors (invalid/unprocessable) from system errors (DB/network) to decide between reject/quarantine and retry.

### 9.4. When header x-event-id is altered in transit

If an HTTP reverse proxy, broker bridge, or header mapper renames it to X-Event-ID or event_id, an exact Map lookup for `"x-event-id"` may miss it. At **each adapter**, normalize casing/names per protocol and publish the mapping; never implicitly assume the same header name works across every transport.

## 10. Internal processing: Service Activator receiving domain payload and trusted headers

After inbound mapping, the business handler does not need to know whether the transport was HTTP, JMS, AMQP, or file. It receives a typed OrderCommand and verified identity.

### 10.1. Demo processor with in-memory idempotency

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

final class DemoOrderProcessor {
    private record Recorded(
            OrderCommand original,
            String businessCorrelationKey,
            OrderAccepted accepted) {
    }

    private final ConcurrentMap<String, Recorded> ledger =
            new ConcurrentHashMap<>();

    OrderAccepted process(
            OrderCommand command,
            String tenantId,
            String producerId,
            String eventId,
            String businessKey) {

        String expected = "order:" + tenantId
                + ":" + command.orderId()
                + ":epoch-" + command.workflowEpoch();
        if (!expected.equals(businessKey)) {
            throw new SecurityException(
                    "BUSINESS_CORRELATION_MISMATCH");
        }

        String dedupKey =
                tenantId + ":" + producerId + ":" + eventId;

        Recorded stored = ledger.compute(dedupKey, (key, existing) -> {
            if (existing != null) {
                if (!existing.original().equals(command)
                        || !existing.businessCorrelationKey()
                                .equals(businessKey)) {
                    throw new IllegalStateException(
                            "EVENT_ID_CONFLICT");
                }
                return existing;
            }

            return new Recorded(
                    command,
                    businessKey,
                    new OrderAccepted(
                            tenantId,
                            producerId,
                            eventId,
                            command.orderId(),
                            "ACCEPTED"));
        });
        return stored.accepted();
    }

    int uniqueEventCount() {
        return ledger.size();
    }
}
~~~

In the example, ConcurrentHashMap ensures sequential updates per key within the same JVM. **This is not a production ledger**: it does not survive restarts, does not coordinate across instances, and does not guarantee exactly-once external side effects. When a handler writes to a database, calls a carrier, or charges a payment, dedicated transactions, idempotency keys, and recovery are required.

### 10.2. Service Activator receiving method arguments

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

final class OrderProcessingActivator {
    private final DemoOrderProcessor processor;

    OrderProcessingActivator(DemoOrderProcessor processor) {
        this.processor = processor;
    }

    @ServiceActivator(
            inputChannel = "trustedCommands",
            outputChannel = "orderResults")
    public OrderAccepted accept(
            @Payload OrderCommand command,
            @Header("trustedTenantId") String tenantId,
            @Header("producerId") String producerId,
            @Header("businessEventId") String eventId,
            @Header("businessCorrelationKey") String businessKey) {

        return processor.process(
                command, tenantId, producerId, eventId, businessKey);
    }
}
~~~

This is where **Channel Adapter** and **Service Activator** meet: the inbound adapter sanitizes and normalizes payloads/headers; the handler executes business logic via typed arguments. Never let business methods directly read HTTP `X-Tenant-Id` or broker delivery tags.

### 10.3. Why does the processor re-verify the business key?

An intermediate Transformer or custom handler could accidentally alter businessCorrelationKey. A handler with side effects should verify critical invariants before committing, while trusting tenantId only after ingress authorization. Comparing two matching strings **does not replace** producer authentication.

## 11. Outbound mapper: domain result to wire payload and selected headers

On the outbound side, we want to **preserve the business event ID** for the partner without exporting internal tenant context, implementation details, or MessageChannel objects.

### 11.1. OutboundPacket holding the transport contract

~~~java
import java.util.Map;
import java.util.Objects;

record OutboundPacket(
        String jsonBody,
        Map<String, String> nativeHeaders) {

    OutboundPacket {
        Objects.requireNonNull(jsonBody, "jsonBody");
        nativeHeaders = Map.copyOf(nativeHeaders);
    }
}
~~~

Map.copyOf prevents arbitrary mutation of native headers after packet creation. If the payload is a byte[], apply defensive copying in both constructor and accessor; a Java record holding a byte[] is not deeply immutable on its own.

### 11.2. Encoder producing wire ACK v1

~~~java
import java.util.Map;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class OrderOutboundMapper {
    private final ObjectMapper objectMapper;

    OrderOutboundMapper(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    Message<OutboundPacket> toWire(Message<OrderAccepted> input) {
        OrderAccepted accepted = input.getPayload();

        // If the handler received headers, they must remain consistent
        // at this hop. If missing, fail to catch regressions.
        Object eventHeader =
                input.getHeaders().get("businessEventId");
        Object tenantHeader =
                input.getHeaders().get("trustedTenantId");
        if (!accepted.eventId().equals(eventHeader)
                || !accepted.tenantId().equals(tenantHeader)) {
            throw new SecurityException(
                    "OUTBOUND_METADATA_MISMATCH");
        }

        OrderAckWireV1 wire = new OrderAckWireV1(
                1,
                accepted.eventId(),
                accepted.orderId(),
                accepted.outcome());

        String json;
        try {
            json = objectMapper.writeValueAsString(wire);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                    "ACK_SERIALIZATION_FAILED", ex);
        }

        OutboundPacket packet = new OutboundPacket(
                json,
                Map.of(
                        "content-type", "application/json",
                        "x-event-id", accepted.eventId(),
                        "x-schema-version", "1"));

        // Create a new Message for transport output.
        // Native headers are encapsulated in the allowlisted packet.
        return MessageBuilder.withPayload(packet).build();
    }
}
~~~

**What to test:** the headers of Message<OrderAccepted> must survive across the Service Activator. When a handler returns a plain payload, Spring Integration generally propagates headers; if a handler returns a new Message or a HeaderFilter intervenes, behavior can differ. Integration tests verify this rather than relying on assumptions.

### 11.3. Why not use copyHeaders(input.getHeaders())?

~~~java
// Anti-pattern if the entire Message will be serialized to the transport.
return MessageBuilder.withPayload(packet)
        .copyHeaders(input.getHeaders())
        .build();
~~~

Input headers may contain technical correlationId/sequenceNumber, replyChannel/errorChannel, trace context, tenantId, and security-sensitive data. If an outbound sink forwards everything, it risks data leaks or routing manipulation. OutboundPacket carries only **the native headers published in contract v1**.

### 11.4. Do not trust an internal Message merely because it is inside the JVM

If an internal component accepts an untrusted Spring Message directly and feeds it to `trustedCommands`, the mere presence of `trustedTenantId` does not make it trustworthy. Channel ownership, producers, interceptors, and ingress must be locked down. Even though the outbound mapper checks metadata consistency, that cannot substitute for authorization.

## 12. Spring Integration wiring: adapter harness across channels

To test the full path, we create four DirectChannels and annotated endpoints:

~~~mermaid
flowchart LR
    A["TransportFrame input"] --> R["transportFrames"]
    R --> I["@Transformer: inbound mapper"]
    I --> C["trustedCommands"]
    C --> S["@ServiceActivator: process"]
    S --> O["orderResults"]
    O --> E["@Transformer: outbound mapper"]
    E --> P["transportPackets"]
    P --> K["@ServiceActivator: collecting sink"]
~~~

### 12.1. Inbound Transformer

~~~java
import org.springframework.integration.annotation.Transformer;
import org.springframework.messaging.Message;

final class OrderInboundTransformer {
    private final OrderInboundMapper mapper;

    OrderInboundTransformer(OrderInboundMapper mapper) {
        this.mapper = mapper;
    }

    @Transformer(
            inputChannel = "transportFrames",
            outputChannel = "trustedCommands")
    public Message<OrderCommand> normalize(TransportFrame frame) {
        return mapper.toTrustedMessage(frame);
    }
}
~~~

In the harness, **transportFrames** receives Messages sent by the test suite acting as the inbound adapter. In production, a real HTTP/JMS/AMQP/file adapter receives from the external source and invokes/feeds the equivalent mapping logic. Do not mistake using @Transformer here for having built a network adapter.

### 12.2. Outbound Transformer

~~~java
import org.springframework.integration.annotation.Transformer;
import org.springframework.messaging.Message;

final class OrderOutboundTransformer {
    private final OrderOutboundMapper mapper;

    OrderOutboundTransformer(OrderOutboundMapper mapper) {
        this.mapper = mapper;
    }

    @Transformer(
            inputChannel = "orderResults",
            outputChannel = "transportPackets")
    public Message<OutboundPacket> encode(
            Message<OrderAccepted> resultMessage) {
        return mapper.toWire(resultMessage);
    }
}
~~~

### 12.3. Outbound sink simulating Channel Adapter

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.springframework.integration.annotation.ServiceActivator;

final class CollectingOutboundAdapter {
    private final CopyOnWriteArrayList<OutboundPacket> sent =
            new CopyOnWriteArrayList<>();

    @ServiceActivator(inputChannel = "transportPackets")
    public void send(OutboundPacket packet) {
        sent.add(packet);
    }

    List<OutboundPacket> packets() {
        return List.copyOf(sent);
    }

    void clear() {
        sent.clear();
    }
}
~~~

This is an **in-memory test sink**, not a JMS/AMQP sender. In a real deployment, the outbound adapter serializes and sends the packet with proper content type and native headers, handling send failures, confirms, or outbox persistence accordingly.

### 12.4. Configuration

~~~java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class OrderAdapterHarnessConfig {

    @Bean
    MessageChannel transportFrames() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel trustedCommands() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel orderResults() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel transportPackets() {
        return new DirectChannel();
    }

    @Bean
    ObjectMapper orderObjectMapper() {
        return new ObjectMapper().configure(
                DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, true);
    }

    @Bean
    OrderSourceAuthorization demoOrderAuthorization() {
        // For demonstration/testing only! This is NOT real authentication.
        return (producer, event) -> {
            if (!"partner-a".equals(producer.producerId())) {
                throw new SecurityException("PRODUCER_NOT_ALLOWED");
            }
        };
    }

    @Bean
    OrderInboundMapper orderInboundMapper(
            ObjectMapper mapper,
            OrderSourceAuthorization authorization) {
        return new OrderInboundMapper(mapper, authorization);
    }

    @Bean
    OrderOutboundMapper orderOutboundMapper(ObjectMapper mapper) {
        return new OrderOutboundMapper(mapper);
    }

    @Bean
    DemoOrderProcessor demoOrderProcessor() {
        return new DemoOrderProcessor();
    }

    @Bean
    OrderInboundTransformer orderInboundTransformer(
            OrderInboundMapper mapper) {
        return new OrderInboundTransformer(mapper);
    }

    @Bean
    OrderProcessingActivator orderProcessingActivator(
            DemoOrderProcessor processor) {
        return new OrderProcessingActivator(processor);
    }

    @Bean
    OrderOutboundTransformer orderOutboundTransformer(
            OrderOutboundMapper mapper) {
        return new OrderOutboundTransformer(mapper);
    }

    @Bean
    CollectingOutboundAdapter collectingOutboundAdapter() {
        return new CollectingOutboundAdapter();
    }
}
~~~

In production code, real adapter beans replace both ends of the test harness; never use demoOrderAuthorization as a security policy. Jackson 2 (as in the snippets) fits many Spring Integration 6.x projects; adjust dependencies/imports to your framework version if your project has migrated Jackson APIs.

### 12.5. Sending a test frame

~~~java
String json = """
        {
          "schemaVersion": 1,
          "eventId": "evt-order-901",
          "orderId": "ORD-901",
          "sku": "SKU-RED",
          "quantity": 2,
          "workflowEpoch": 3
        }
        """;

TransportFrame frame = new TransportFrame(
        json,
        Map.of(
                "x-event-id", "evt-order-901",
                "x-tenant-id", "tenant-admin"),
        new VerifiedProducer("tenant-a", "partner-a"));

// In a test/application with a Spring context:
transportFrames.send(
        org.springframework.messaging.support.MessageBuilder
                .withPayload(frame)
                .build());
~~~

**Expectation:** the outbound packet contains eventId evt-order-901 and the JSON ACK, does not contain `x-tenant-id` from the raw header, and does not emit `trustedTenantId` over the wire. This tests the most crucial rule: **preserve business identity without copying unverified external data**.

## 13. Inbound unit tests: valid payload and headers, spoofed sources rejected

Unit tests isolate the mapper from framework endpoints to verify payload/header conversion and the trust boundary.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;

class OrderInboundMapperTest {
    private OrderInboundMapper mapper;

    @BeforeEach
    void prepare() {
        ObjectMapper jackson = new ObjectMapper().configure(
                DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, true);
        OrderSourceAuthorization auth = (producer, wire) -> {
            if (!"partner-a".equals(producer.producerId())) {
                throw new SecurityException("PRODUCER_NOT_ALLOWED");
            }
        };
        mapper = new OrderInboundMapper(jackson, auth);
    }

    private String json(String eventId, int quantity) {
        return """
                {
                  "schemaVersion": 1,
                  "eventId": "%s",
                  "orderId": "ORD-901",
                  "sku": "SKU-RED",
                  "quantity": %d,
                  "workflowEpoch": 3
                }
                """.formatted(eventId, quantity);
    }

    private TransportFrame frame(
            String eventId,
            Map<String, String> wireHeaders) {
        return new TransportFrame(
                json(eventId, 2),
                wireHeaders,
                new VerifiedProducer("tenant-a", "partner-a"));
    }

    @Test
    void mapsPayloadIntoTypedOrderCommand() {
        Message<OrderCommand> output =
                mapper.toTrustedMessage(frame(
                        "evt-order-901",
                        Map.of("x-event-id", "evt-order-901")));

        OrderCommand command = output.getPayload();
        assertEquals("ORD-901", command.orderId());
        assertEquals("SKU-RED", command.sku());
        assertEquals(2, command.quantity());
        assertEquals(3, command.workflowEpoch());
    }

    @Test
    void createsTrustedHeadersWithoutCopyingExternalHeaders() {
        Message<OrderCommand> output =
                mapper.toTrustedMessage(frame(
                        "evt-order-902",
                        Map.of(
                                "x-event-id", "evt-order-902",
                                "x-tenant-id", "tenant-admin",
                                "replyChannel", "maliciousChannel")));

        assertEquals("tenant-a",
                output.getHeaders().get("trustedTenantId"));
        assertEquals("partner-a",
                output.getHeaders().get("producerId"));
        assertEquals("evt-order-902",
                output.getHeaders().get("businessEventId"));
        assertEquals(
                "order:tenant-a:ORD-901:epoch-3",
                output.getHeaders().get("businessCorrelationKey"));

        assertNull(output.getHeaders().get("x-tenant-id"));
        assertNull(output.getHeaders().get("replyChannel"));
    }

    @Test
    void rejectsHeaderAndPayloadEventIdMismatch() {
        TransportFrame frame = frame(
                "evt-order-903",
                Map.of("x-event-id", "evt-other"));

        assertThrows(SecurityException.class,
                () -> mapper.toTrustedMessage(frame));
    }

    @Test
    void rejectsUnauthorizedProducer() {
        TransportFrame frame = new TransportFrame(
                json("evt-order-904", 1),
                Map.of(),
                new VerifiedProducer("tenant-a", "unknown-producer"));

        assertThrows(SecurityException.class,
                () -> mapper.toTrustedMessage(frame));
    }

    @Test
    void rejectsMalformedJson() {
        TransportFrame frame = new TransportFrame(
                "{not-valid-json",
                Map.of(),
                new VerifiedProducer("tenant-a", "partner-a"));

        assertThrows(IllegalArgumentException.class,
                () -> mapper.toTrustedMessage(frame));
    }

    @Test
    void rejectsInvalidQuantity() {
        TransportFrame frame = new TransportFrame(
                json("evt-order-905", 0),
                Map.of(),
                new VerifiedProducer("tenant-a", "partner-a"));

        assertThrows(IllegalArgumentException.class,
                () -> mapper.toTrustedMessage(frame));
    }

    @Test
    void rejectsUnknownFieldsUnderStrictContract() {
        String unknownField = """
                {
                  "schemaVersion": 1,
                  "eventId": "evt-order-906",
                  "orderId": "ORD-901",
                  "sku": "SKU-RED",
                  "quantity": 2,
                  "workflowEpoch": 3,
                  "unexpectedControlChannel": "admin"
                }
                """;

        TransportFrame frame = new TransportFrame(
                unknownField, Map.of(),
                new VerifiedProducer("tenant-a", "partner-a"));

        assertThrows(IllegalArgumentException.class,
                () -> mapper.toTrustedMessage(frame));
    }
}
~~~

**What this tests:** the mapper produces a typed payload; trusted custom headers are derived from verified context; raw x-tenant-id/replyChannel are never copied; mismatched eventId, unauthorized producers, malformed JSON, and validation errors are rejected.

**What remains untested:** whether a real HTTP/JMS adapter normalizes header names/content types into the exact shape of TransportFrame; how mTLS/JWT/ACL actually produces VerifiedProducer; broker ACKs/retries and database side effects.

### 13.1. Strict unknown fields is a policy, not a universal rule

The example uses **FAIL_ON_UNKNOWN_PROPERTIES=true** to catch non-compliant v1 payloads early. A system requiring forward/backward compatibility may allow unknown optional fields, but must decide explicitly based on schema/version. Never silently ignore fields affecting authorization, currency, or semantics.

### 13.2. Data type conversion is part of the contract

One producer might send quantity as String **"2"** while another sends JSON number **2**. With coercion enabled in ObjectMapper, both become int, potentially letting malformed input slip through. When enforcing a strict schema, disable unwanted coercions and add tests for numbers, Strings, null, and overflow/negative values.

## 14. Outbound unit tests: selecting wire fields without leaking headers

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class OrderOutboundMapperTest {

    private final ObjectMapper jackson = new ObjectMapper();
    private final OrderOutboundMapper mapper =
            new OrderOutboundMapper(jackson);

    private Message<OrderAccepted> acceptedMessage() {
        return MessageBuilder.withPayload(
                new OrderAccepted(
                        "tenant-a",
                        "partner-a",
                        "evt-order-901",
                        "ORD-901",
                        "ACCEPTED"))
                .setHeader("trustedTenantId", "tenant-a")
                .setHeader("businessEventId", "evt-order-901")
                .setHeader(
                        "businessCorrelationKey",
                        "order:tenant-a:ORD-901:epoch-3")
                .setHeader("internalRiskScore", 99)
                .build();
    }

    @Test
    void producesVersionedJsonAndSelectedNativeHeaders()
            throws Exception {
        Message<OutboundPacket> output =
                mapper.toWire(acceptedMessage());

        OutboundPacket packet = output.getPayload();
        JsonNode root = jackson.readTree(packet.jsonBody());

        assertEquals(1, root.path("schemaVersion").asInt());
        assertEquals("evt-order-901",
                root.path("eventId").asText());
        assertEquals("ORD-901",
                root.path("orderId").asText());
        assertEquals("ACCEPTED",
                root.path("outcome").asText());
        assertTrue(root.path("tenantId").isMissingNode());
        assertTrue(root.path("internalRiskScore").isMissingNode());

        assertEquals(
                Map.of(
                        "content-type", "application/json",
                        "x-event-id", "evt-order-901",
                        "x-schema-version", "1"),
                packet.nativeHeaders());
        assertFalse(
                packet.nativeHeaders()
                        .containsKey("trustedTenantId"));
        assertFalse(
                packet.nativeHeaders()
                        .containsKey("businessCorrelationKey"));
    }

    @Test
    void rejectsHeaderPayloadIdentityMismatch() {
        Message<OrderAccepted> forged =
                MessageBuilder.withPayload(
                        new OrderAccepted(
                                "tenant-a",
                                "partner-a",
                                "evt-order-901",
                                "ORD-901",
                                "ACCEPTED"))
                .setHeader("trustedTenantId", "tenant-b")
                .setHeader("businessEventId", "evt-order-901")
                .build();

        assertThrows(SecurityException.class,
                () -> mapper.toWire(forged));
    }
}
~~~

The test verifies **the public surface of OutboundPacket** rather than just internal MessageHeaders. This distinction matters: the internal Message can retain context for observability, while the outbound transport contract must expose only selected fields.

### 14.1. What risks does header duplication pose?

When eventId appears in both the body and x-event-id, the transport receiver must enforce consistency or define which source is authoritative. Never let a sender mutate one of the two and have downstream pick arbitrarily, causing broken deduplication.

### 14.2. Copy-on-write and immutability

A wire packet of String JSON + Map.copyOf suffices for illustration. For byte arrays, streaming buffers, or file handles, enforce ownership/defensive copies and never share mutable state unchecked across PublishSubscribeChannel subscribers.

## 15. Spring integration test: end-to-end inbound mapper → outbound sink

This integration test boots **OrderAdapterHarnessConfig**, sends a TransportFrame simulating an inbound adapter, and asserts the packet received by the outbound sink.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(OrderAdapterHarnessConfig.class)
class OrderAdapterHarnessIntegrationTest {

    @Autowired
    @Qualifier("transportFrames")
    MessageChannel input;

    @Autowired
    CollectingOutboundAdapter output;

    @Autowired
    DemoOrderProcessor processor;

    @Autowired
    ObjectMapper jackson;

    @BeforeEach
    void resetOutput() {
        output.clear();
    }

    private TransportFrame frame(
            String eventId,
            String tenantId,
            int quantity) {
        String json = """
                {
                  "schemaVersion": 1,
                  "eventId": "%s",
                  "orderId": "ORD-901",
                  "sku": "SKU-RED",
                  "quantity": %d,
                  "workflowEpoch": 3
                }
                """.formatted(eventId, quantity);

        return new TransportFrame(
                json,
                Map.of(
                        "x-event-id", eventId,
                        "x-tenant-id", "tenant-admin"),
                new VerifiedProducer(tenantId, "partner-a"));
    }

    private void send(TransportFrame frame) {
        assertTrue(input.send(
                MessageBuilder.withPayload(frame).build()));
    }

    @Test
    void validInputBecomesOutboundAckWithSelectedHeaders()
            throws Exception {

        send(frame("evt-flow-901", "tenant-a", 2));

        assertEquals(1, output.packets().size());
        OutboundPacket packet = output.packets().get(0);

        JsonNode root = jackson.readTree(packet.jsonBody());
        assertEquals("evt-flow-901",
                root.path("eventId").asText());
        assertEquals("ORD-901",
                root.path("orderId").asText());
        assertEquals("ACCEPTED",
                root.path("outcome").asText());
        assertEquals("evt-flow-901",
                packet.nativeHeaders().get("x-event-id"));
        assertNull(
                packet.nativeHeaders().get("x-tenant-id"));
        assertNull(
                packet.nativeHeaders().get("replyChannel"));
    }

    @Test
    void duplicateEventReplaysAckWithoutCreatingSecondRecord() {
        int before = processor.uniqueEventCount();
        TransportFrame event =
                frame("evt-flow-duplicate", "tenant-a", 2);

        send(event);
        send(event);

        assertEquals(before + 1, processor.uniqueEventCount());
        assertEquals(2, output.packets().size());
        assertEquals(
                output.packets().get(0).jsonBody(),
                output.packets().get(1).jsonBody());
    }

    @Test
    void conflictingPayloadUnderSameEventIdFails() {
        send(frame("evt-flow-conflict", "tenant-a", 2));

        assertThrows(RuntimeException.class,
                () -> send(
                        frame("evt-flow-conflict", "tenant-a", 3)));

        assertEquals(1, output.packets().size());
    }

    @Test
    void sameEventIdDifferentTenantsDoNotCollide() {
        int before = processor.uniqueEventCount();

        send(frame("evt-flow-tenant", "tenant-a", 2));
        send(frame("evt-flow-tenant", "tenant-b", 2));

        assertEquals(before + 2, processor.uniqueEventCount());
        assertEquals(2, output.packets().size());
    }

    @Test
    void badEventHeaderIsRejectedBeforeSink() {
        TransportFrame bad = new TransportFrame(
                """
                {
                  "schemaVersion": 1,
                  "eventId": "evt-flow-bad",
                  "orderId": "ORD-901",
                  "sku": "SKU-RED",
                  "quantity": 2,
                  "workflowEpoch": 3
                }
                """,
                Map.of("x-event-id", "evt-different"),
                new VerifiedProducer("tenant-a", "partner-a"));

        assertThrows(RuntimeException.class, () -> send(bad));
        assertTrue(output.packets().isEmpty());
    }
}
~~~

### 15.1. What the test proves

- Spring Integration registers the annotated Transformer and Service Activator endpoints.
- Messages flow synchronously through the channel chain as designed.
- Payloads convert JSON → typed OrderCommand → OrderAccepted → ACK JSON.
- Business identity stays intact and outbound native headers are allowlisted.
- Same-event replay within the same JVM does not create a new record in the demo processor.
- The same event ID across two tenants does not collide when the ledger namespaces properly.
- Mismatched event headers or event conflicts produce no new success output.

### 15.2. What the test does not prove

- That a specific HTTP/JMS/AMQP/TCP header mapper works properly over the network.
- Real authentication/authorization against an external producer.
- Correct event ACK/requeue on broker redelivery.
- Transactional inbox/outbox resilience across process restarts.
- Exactly-once external side effects or distributed commits.
- Behavior when DirectChannel is replaced by ExecutorChannel/QueueChannel.

**This is a mapping contract test inside the Spring runtime, not an end-to-end network adapter test.**

## 16. HTTP adapter: body and headers are two separate data channels

With HTTP, a request has **method, URI, status, content type, body, and headers**. The adapter can construct a Spring Message from the request and choose the body as the payload; native HTTP headers do not automatically become application custom headers.

~~~text
POST /external/orders/events
Content-Type: application/json
X-Event-Id: evt-order-901
X-Tenant-Id: tenant-admin

{"schemaVersion":1,"eventId":"evt-order-901", ...}
~~~

A safe inbound boundary:

~~~mermaid
flowchart TD
    H["HTTP request"] --> A["Authentication + content-type/size limits"]
    A --> P["Parse JSON + schema validation"]
    P --> V["Authorize tenant/order + event identity"]
    V --> M["Create trusted Spring Message"]
    M --> C["Internal channel"]
~~~

### 16.1. HTTP inbound channel adapter vs. HTTP inbound gateway

- **Inbound Channel Adapter:** suited for one-way ingestion, e.g., receiving a notification/event and emitting it onto a channel; the HTTP response typically confirms transport/acceptance level per configuration.
- **Inbound Gateway:** suited for an HTTP request expecting a Spring Message reply mapped back to the HTTP response.

If `POST /quote` must return a price synchronously, a **Gateway** usually fits the semantics better than a one-way adapter. If an endpoint only ingests events for a later workflow, **adapter + durable ingestion/accepted policy** can make sense.

### 16.2. HeaderMapper requires an allowlist policy

Example published mapping:

| HTTP source | Inbound handling | Spring internal header |
| --- | --- | --- |
| `Content-Type` | Validate JSON media type | Used only for converter/content-type |
| `X-Event-Id` | Validate and cross-check body.eventId | `businessEventId` |
| `X-Tenant-Id` | Use as claimed tenant for cross-check if needed | **Never** promoted directly to trustedTenantId |
| `X-Trace-Ref` | Validate length/charset | `externalTraceRef` per contract |
| `Authorization` | Consumed by authentication filter | Never echoed to domain/outbound |
| `X-Reply-Channel` | Prevent clients from controlling MessageChannel | Drop/reject |

In Spring Integration HTTP, `HeaderMapper` and `HttpMessageConverter` address different concerns. The converter transforms body/Java objects, whereas HeaderMapper transfers selected HTTP headers. Security filters/controllers/verification layers establish trust.

### 16.3. Content-Type does not mean the actual payload is valid

`Content-Type: application/json` does not prove the body is schema-valid JSON. Validate encoding, body size, and actually parse it. If an API requires JSON v1, an unknown `schemaVersion=99` must enter the unsupported-version path rather than silently parsing as v1.

### 16.4. HTTP status contract

An event ingestion API might publish:

- 202 Accepted: command/event accepted at the boundary for downstream processing per contract.
- 400 Bad Request: malformed JSON or missing required fields.
- 401/403: authentication or authorization failure.
- 409 Conflict: eventId/operationId reused with a different payload.
- 415 Unsupported Media Type: unsupported Content-Type.
- 422 Unprocessable Content: syntactically valid schema violating business field policies.
- 429/503: rate-limited or temporarily unavailable.

These are **contract suggestions**, not Spring Integration's default status mappings. If an adapter returns 202 before persisting the command, document the possibility of event loss on process crash.

## 17. JMS adapter: Java Message headers differ from JMS headers/properties

JMS has **JMSMessageID, JMSCorrelationID, JMSReplyTo, JMSType**, and application properties. Spring Integration JMS adapters convert a JMS Message into a Spring Message via converter/header mapper and vice versa.

~~~text
JMS TextMessage:
  body = {"schemaVersion":1,...}
  JMSMessageID = ID:...
  JMSCorrelationID = some-protocol-token
  property event_id = evt-order-901

JMS inbound adapter
  -> MessageConverter / HeaderMapper
  -> Spring Message<OrderWireV1 / String / byte[]>
  -> Trusted normalization
  -> Message<OrderCommand>
~~~

### 17.1. Two different mapping directions

| JMS concept | Spring concept | Note |
| --- | --- | --- |
| JMS TextMessage body | String payload or converted DTO | Depends on converter |
| JMS BytesMessage body | byte[] payload or DTO | Bound size, encoding/schema |
| JMSMessageID | Native JMS transport identity | Does not replace businessEventId |
| JMSCorrelationID | Protocol correlation | Does not automatically act as workflow correlation |
| JMSReplyTo | JMS request/reply destination | Not a Spring temporary MessageChannel |
| Custom JMS property event_id | Custom Spring header if mapped | Needs name/type contract |
| JMS redelivery flag | Delivery metadata | Retry signal only, does not guarantee dedup |

### 17.2. HeaderMapper is not a content converter

In Spring Integration JMS support, there are JMS header mapping classes such as **DefaultJmsHeaderMapper** along with JMS payload converters. Mapper configuration controls which properties/headers enter the Spring Message. Converter configuration controls how TextMessage/BytesMessage/JSON bodies map to Java payloads.

If the broker property `event_id` enters Spring headers while the payload is still a JSON String, mapping is **incomplete**: you still need to parse into OrderWireV1, validate the schema, and build OrderCommand.

### 17.3. JMS properties have type restrictions

JMS properties support protocol-defined primitive/String types; never assume an arbitrary Java object like MessageChannel, DomainEnvelope, or RequestContext can be copied as a property. Send only portable wire-contract values such as String/boolean/number where valid.

### 17.4. Ack and transaction

JMS inbound adapters have ACK/session transaction/poller semantics depending on configuration. If a handler performs an external side effect and the session rolls back due to a reply/send failure, the message can be redelivered. Hence businessEventId/operationId must be stable and downstream effects idempotent.

### 17.5. Do not use JMSCorrelationID for business deduplication

A request may be retried with a **different JMSCorrelationID** for a new request/reply attempt while keeping the same businessEventId. Deduplicating by a protocol correlation token risks executing effects twice. Derive dedup scope from verified business identity.

## 18. AMQP adapter: properties, headers, and broker confirms

AMQP (e.g., RabbitMQ) typically includes **contentType, correlationId, replyTo, deliveryMode, routingKey, application headers** alongside payload bytes. Message converters and header mappers convert between these and Spring Messages.

~~~text
AMQP:
  body = UTF-8 JSON bytes
  contentType = application/json
  headers.event_id = evt-order-901
  correlationId = request-attempt-123
  replyTo = reply-queue-for-attempt

Inbound mapping:
  converter -> OrderWireV1
  header policy -> permitted metadata
  verifier -> trusted producer/tenant
  transformer -> OrderCommand
~~~

### 18.1. A publisher confirm is not OrderAccepted

A broker confirm verifies the broker received the message. It **does not prove** the consumer Service Activator persisted data or returned a business result. When the caller needs the outcome, use a request/reply Gateway or an asynchronous completion contract.

### 18.2. Scoping correlation IDs

AMQP `correlationId` may be used by an outbound gateway to match replies to request attempts. It does not necessarily equal the order's `businessCorrelationKey`. If a message is resent after a timeout with a new attempt token, the business identity must remain unchanged.

### 18.3. Retry and DLQ

When a consumer fails, depending on listener/container policy the message may be requeued, retried, or sent to a DLQ. **Malformed schemas or unauthorized messages** should not be retried infinitely like transient network errors. Use dead-letter/quarantine queues with reason codes and replay policies that prevent duplicate side effects.

### 18.4. Portable header types

Never send arbitrary Java class instances in AMQP application headers. Use portable, schema-backed values; for nested business metadata, consider a JSON/Avro/Protobuf wire envelope rather than hoping HeaderMapper serializes arbitrary objects.

## 19. File/SFTP adapter: payload may be File, not JSON String

File inbound adapters typically emit messages carrying **java.io.File** or file contents depending on source and configuration. A Service Activator expecting `OrderCommand` will not automatically receive the DTO when the payload is a File.

~~~mermaid
flowchart LR
    D["Incoming directory"] --> F["File inbound adapter"]
    F --> M["Message<File>"]
    M --> P["Read bounded bytes + UTF-8 decode"]
    P --> J["Validate JSON schema / origin"]
    J --> T["OrderCommand + trusted metadata"]
    T --> S["Service Activator"]
~~~

### 19.1. A filename is metadata, not authorization

A file named `tenant-admin_orders.json` does not prove it belongs to tenant-admin. With SFTP, bind the authenticated remote account/directory/transport identity to permitted tenants rather than trusting filename parsing alone.

### 19.2. Large file payloads and streaming

Never blindly call `Files.readString(file)` on multi-GB files. Check size limits, read permissions, symlinks/path traversal, and use a streaming parser when needed. With file-based polling, apply filters/locks/rename policies to avoid reading partially written files or reprocessing uncontrollably.

### 19.3. Outbound filenames must be safe

Never allow an untrusted `orderId="../../secrets"` to dictate a write path. Use a sanitized basename, fixed target directory, collision policy, and atomic write/rename when durability is required.

### 19.4. A single file may contain multiple events

If each file holds a batch of orders, use a Splitter to break out records and assign stable **child logical IDs** plus batch correlation/group semantics. Never use `sequenceNumber` alone as an idempotency key; use parent batch ID + child ID or a properly scoped composite key.

## 20. TCP and transports without rich header metadata

TCP is a byte stream with no built-in business message boundaries. Spring Integration TCP adapters/gateways need framing/serializers/deserializers to delimit each frame. If payloads carry eventId/tenantRef, deserialize using a **versioned envelope** and verify source/tenant upon receipt.

~~~text
TCP bytes
   -> framing (length-prefixed / delimiter / custom)
   -> versioned wire envelope
   -> validate message length and schema
   -> bind authenticated connection identity
   -> Spring Message<DomainCommand>
~~~

Never treat a TCP connection ID as a business correlation key. Multiple requests can share one connection, and one logical operation can retry on a new connection.

## 21. Technical comparison of mapping across adapters

| Source | Typical initial payload | Typical native headers | Deliberate conversion needed |
| --- | --- | --- | --- |
| HTTP | String/byte[]/DTO per converter | Headers, URI, method, content type | JSON schema + trusted principal |
| JMS | TextMessage/BytesMessage/converted object | JMSMessageID, JMSCorrelationID, properties | JMS MessageConverter + HeaderMapper |
| AMQP | byte[]/converted DTO | contentType, routing key, replyTo, application headers | AMQP converter/header mapping |
| File | File or contents | File name/path, timestamp, filter metadata | Bounded file read + decoder |
| SFTP | Local file representing downloaded content | Remote path/source account | Authenticated source binding + path safety |
| TCP | byte[]/String frame | Connection metadata | Framing + versioned envelope |
| In-process | Typed Java object | Spring MessageHeaders | Normalize header contracts between flows |

**The invariant:** input to business services should be normalized into a **domain payload + trusted context** contract, independent of the source adapter. Swapping an adapter should never force Router or Service Activator to learn protocol-specific native header names.

## 22. Header propagation across Router, Transformer, Splitter, and Gateway

Once an adapter builds a Spring Message with trusted headers, the message traverses multiple endpoints. Distinguish **business metadata that must be preserved** from **technical metadata that changes with topology**.

~~~mermaid
flowchart TD
    I["Inbound Adapter"] --> N["Normalize payload + trusted headers"]
    N --> R{"Router by business type"}
    R --> T["Transformer"]
    T --> S["Service Activator"]
    S --> O["Outbound Adapter"]
    R --> P["Splitter / Aggregator flow"]
    P --> O
~~~

### 22.1. When a Transformer returns a plain payload

A Spring Integration Transformer generally propagates inbound headers when returning a new payload. For example, an incoming **OrderWireV1** payload is transformed into **OrderCommand**, and the framework builds the output Message preserving metadata according to endpoint rules.

However, **not every transformation retains all headers**: a HeaderFilter, a gateway/adapter boundary, or a custom handler returning a newly constructed Message can drop fields. Contract tests should assert businessEventId, trustedTenantId, and correlationKey across critical hops.

### 22.2. When a handler constructs a new Message

~~~java
// Example of rebuilding a Message with selected headers:
Message<OrderCommand> next = MessageBuilder
        .withPayload(command)
        .setHeader("trustedTenantId", verifiedTenant)
        .setHeader("businessEventId", stableEventId)
        .setHeader("businessCorrelationKey", businessKey)
        .build();
~~~

Do not see a valid payload and assume the contract is intact. If a downstream Service Activator expects `@Header("businessEventId")`, a missing header causes method argument resolution to fail before the business method runs.

### 22.3. When is HeaderFilter used?

HeaderFilter can strip metadata that should not enter the next branch, such as external trace claims, raw transport tags, or unneeded control headers. However, an overly broad filter can delete **businessCorrelationKey**, breaking downstream Aggregators or handlers.

### 22.4. Splitter and sequence headers

A Splitter may attach **correlationId**, **sequenceNumber**, and **sequenceSize** to each child. These serve the **technical group** and do not necessarily match the order's businessCorrelationKey. If a parent message spawns multiple logical child events, each child may need its own child event ID plus parentEventId/causationId.

Do not reuse the same eventId for all child effects if they must deduplicate independently, and do not use sequenceNumber alone to distinguish events across batches.

### 22.5. Gateway and temporary replyChannel

A Messaging Gateway awaiting a reply may use a runtime **temporary replyChannel**. When a request crosses an outbound HTTP/JMS/AMQP Gateway, the transport uses its own reply/correlation protocol. Never serialize a live MessageChannel object as a wire header; if a callback arrives after the Gateway times out, correlate using **persistent business identity**.

### 22.6. Trace propagation differs from business ID

Trace headers link spans and logs, often using conventions like W3C trace context. However, traceId does not prove tenant identity, cannot replace eventId for idempotency, and can change on retries or sampling policies. Preserve business identity even when tracing is disabled.

## 23. Header contract: name, type, ownership, and scope

A contract table is invaluable when multiple adapters serve one IntegrationFlow:

| Field | Internal type | Owner | Allowed on the wire? | On retry? |
| --- | --- | --- | --- | --- |
| **trustedTenantId** | String | Verified ingress/auth | Only if partner contract permits, by authority | Keep exact tenant |
| **producerId** | String | Authenticated source registry | Often unnecessary | Keep same source scope |
| **businessEventId** | String | Bound/validated source identity | Usually required | Keep for same logical event |
| **businessCorrelationKey** | String | Workflow service | If wire contract requires | Keep for same workflow |
| **externalTraceRef** | String | External caller, sanitized | Only when appropriate | Never use as authority |
| **replyChannel** | MessageChannel/runtime | Spring Gateway | **No** | Attempt-specific |
| **errorChannel** | Channel/runtime | Spring integration | **No** | Endpoint-specific |
| **correlationId** | Object/String per topology | Splitter/Aggregator/transport | Per protocol if needed | Scope-specific |
| **sequenceNumber** | Integer | Splitter | Only if wire contract needs | Child-specific |
| **JMSMessageID** | String/JMS native | JMS broker | Native transport field | May change |
| **AMQP deliveryTag** | Number/native | Broker/consumer delivery | Never use as business ID | Changes per delivery |
| **Content-Type** | Media type | Wire contract/adapter | Yes | Matches encoding |

### 23.1. Do not use Spring MessageHeaders.ID as business eventId

If a message is rebuilt across adapters, **Spring MessageHeaders.ID can change**. The businessEventId for the same logical event must stay stable for deduplication. Derive it from the source event ID / operation registry scoped to tenant/producer, rather than generating a fresh UUID every time a Transformer creates a Message.

### 23.2. Do not force business keys into technical correlation scopes

An order workflow may involve nested Splitter/Aggregator groups and remote Gateway calls. If every CORRELATION_ID is forced to equal businessCorrelationKey, nested Aggregators can mix child groups from different stages. Keep business keys separate or configure group-specific correlationStrategies.

### 23.3. Dynamic native header Maps require bounds

Beyond names and types, enforce limits on:

- Maximum header count.
- Key name allowlist, charset/length, and case normalization.
- Transport-portable String/number/boolean values.
- Rejecting duplicate keys that violate the contract.
- Never using untrusted destination/routing keys directly.
- Never copying sensitive security data into message headers unless the receiver requires it.

HeaderMapper converts representations; **source authentication and authorization must happen before trusting any field's semantics**.

## 24. Schema evolution: the adapter is the compatibility boundary

With multiple producers, wire v1 and v2 may coexist in a broker or filesystem after deploying a new application version.

### 24.1. Never silently change field semantics

For example, wire v1:

~~~json
{"quantity": 2, "quantityUnit": "pieces"}
~~~

And wire v2 changes semantics:

~~~json
{"quantity": 2, "quantityUnit": "boxes"}
~~~

If a v1 handler reads only the number 2 without checking the unit, a new adapter could cause inventory shipments to multiply erroneously. Semantic changes are breaking even when JSON field names and data types remain unchanged.

### 24.2. Versioned parser/upcaster

~~~mermaid
flowchart LR
    V1["WireOrderV1"] --> P1["Parse v1"]
    V2["WireOrderV2"] --> P2["Parse v2"]
    P1 --> C["Canonical OrderCommand"]
    P2 --> C
    C --> B["Business flow"]
~~~

Each converter must know:

- Supported schema versions.
- Required vs. optional fields.
- Business-valid defaults.
- Enum migrations or unsupported values.
- Units, currency, and timezone.
- Producer/client identity validation.
- How to construct canonical businessEventId and correlationKey.

### 24.3. Upcasters must not invent identity

If a v1 event lacks operationId that v2 requires, do not generate a random UUID on every replay. Check whether v1 has a stable source ID from which operationId can be deterministically derived; otherwise route it to a controlled migration/quarantine workflow.

### 24.4. Outbound projection per receiver contract

Receiver A still uses ACK v1 while receiver B uses ACK v2. The adapter should pick a serializer based on **configured receiver capability** or negotiated version, not solely from an untrusted header. If a receiver does not support the new version, fail explicitly rather than sending a new payload labeled `x-schema-version: 1`.

### 24.5. Replay and DLQ must be version-aware

A message sitting in a DLQ for two weeks may use schema v1 when the application is already on v2. Recovery workers must retain v1 parsers/upcasters or a migration plan. Never assume all queued messages match the latest deployed code version.

### 24.6. Strict vs. tolerant parsing

- **Strict:** reject unknown fields to catch schema drift early; suitable for tightly controlled boundaries.
- **Controlled tolerant:** ignore unknown optional fields if allowed by contract, while never ignoring security- or business-critical fields.

Toggling Jackson FAIL_ON_UNKNOWN_PROPERTIES should be designed and tested as part of the versioning policy, not chosen arbitrarily.

## 25. Retry, acknowledgments, and side effects at the adapter boundary

When an outbound adapter sends an event, there are at least three distinct levels of "success":

~~~text
1. Producer created and validated the Spring Message.
2. Adapter / broker accepted the transport message.
3. Remote business consumer committed its effect.
~~~

Never infer level 3 from level 1 or 2. With a one-way outbound adapter, business completion can be reported via another event, status API, or audit workflow.

### 25.1. Inbound ACK timing

An inbound broker adapter can ACK:

- Immediately after pulling the Message from the broker.
- After synchronous flow execution succeeds.
- Within a transaction spanning part of the processing.
- Via application-controlled manual acknowledgment.

Exact behavior varies across JMS, AMQP, Kafka, and framework versions. ACKing before persisting an operation risks losing events on crash. Committing side effects before ACKing the broker risks redelivery and duplicate effects on crash.

### 25.2. Outbound send timeout

If an outbound adapter reports a timeout after sending, any of these may have happened:

- Remote/broker never received the packet.
- Broker received it, but the confirm was lost.
- Consumer received/committed, but the reply was lost.

If the packet represents a **side-effecting command**, never mint a fresh operationId and resend unconditionally. Reconcile status or retry with a stable key per contract.

### 25.3. Dedup keys must match the right scope

~~~text
tenantId      = tenant-a
producerId    = partner-a
businessEventId = evt-order-901

Idempotency key:
  tenant-a | partner-a | evt-order-901
~~~

If the same producer reuses eventId with a different payload, that is an **ID_CONFLICT**. If two different producers both use `evt-order-901`, they may be two distinct events if the contract scopes ID uniqueness per producer.

### 25.4. In-memory dedup does not survive restarts

DemoOrderProcessor in the example only holds a ConcurrentHashMap. On process restart, that state is lost. For durability, implement a ledger with a unique index and transactions:

~~~sql
CREATE TABLE order_event_inbox (
    tenant_id VARCHAR(48) NOT NULL,
    producer_id VARCHAR(48) NOT NULL,
    event_id VARCHAR(96) NOT NULL,
    order_id VARCHAR(64) NOT NULL,
    workflow_epoch INTEGER NOT NULL,
    payload_digest VARCHAR(128) NOT NULL,
    processing_state VARCHAR(32) NOT NULL,
    result_reference VARCHAR(160),
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, producer_id, event_id)
);

CREATE INDEX order_event_inbox_state_idx
    ON order_event_inbox (processing_state);
~~~

A row in state RECEIVED does not prove business effects committed. You need a state machine, worker leases/recovery, and—when dispatching to another system—a transactional outbox or equivalent synchronization mechanism.

### 25.5. Crash window

~~~text
1. Adapter receives event.
2. Application writes inbox state=RECEIVED.
3. Application acknowledges broker.
4. Process crashes before business handler runs.
5. Broker will not redeliver; event remains RECEIVED.
~~~

A recovery worker must scan for events stuck in RECEIVED/DISPATCH_PENDING and resume processing. If duplicates are simply dropped because the row already exists, the message can be permanently "lost" despite having an inbox record.

### 25.6. Outbox for outbound publishing

If an application both writes an order to the DB and needs to publish OrderAccepted, it can use a **transactional outbox**:

~~~text
DB transaction:
  UPDATE order state
  INSERT outbox event with stable eventId
COMMIT

Outbox publisher:
  read pending records
  adapter send to broker
  mark as delivered according to policy
~~~

An outbox publisher can still emit the same event more than once after crashes or lost confirms; consumers still need idempotency. Outbox narrows the gap between DB commit and event publication, **without magically creating system-wide exactly-once delivery**.

### 25.7. Retry decision table

| Failure | Should retry? | Reason |
| --- | --- | --- |
| Malformed JSON, unknown schemaVersion | Do not retry raw payload infinitely | Permanent contract issue |
| Header/payload eventId mismatch | Do not dispatch business event | Identity violation |
| Unauthorized producer | Do not retry as transient IO | Security failure |
| External API timeout | Bounded retry possible | Stable operationId / reconcile |
| Database temporarily unavailable | Yes | Backoff + durable recovery |
| Same event replay | May return prior receipt / skip effect | Idempotency |
| Same key, different payload | Do not treat as normal duplicate | Conflict/quarantine |
| Broker confirm lost | Controlled retry | Packet may already have been received |
| Outbound header converter type error | Fix converter/schema | Do not retry infinitely |
| Receiver reports unsupported version | Rollback/upcast/upgrade | Compatibility |

## 26. Error flow: schema errors differ from handler errors and broker errors

An adapter pipeline has multiple failure points:

~~~mermaid
flowchart TD
    A["Inbound transport"] --> V{"Decode / validate"}
    V -->|"Malformed / unsupported"| Q["Reject / quarantine"]
    V -->|"Valid"| B{"Authenticate / authorize"}
    B -->|"Denied"| S["Security rejection"]
    B -->|"Verified"| C{"Internal processing"}
    C -->|"Business reject"| R["Typed business outcome"]
    C -->|"Transient failure"| T["Retry / recover"]
    C -->|"Success"| O{"Outbound convert / send"}
    O -->|"Converter failure"| F["Contract failure"]
    O -->|"Send failed / unknown"| U["Outbox retry / reconcile"]
    O -->|"Transport accepted"| D["Transport delivery status"]
~~~

### 26.1. DirectChannel in the harness

All channels in the example are DirectChannels. An exception in OrderInboundMapper, the processor, or the outbound mapper typically propagates back to `input.send(...)`. Thus negative integration tests can assert RuntimeException and confirm the sink received no success packets.

**Do not generalize** this behavior to QueueChannel, ExecutorChannel, pollers, AMQP listeners, or JMS sessions; threading, errorChannel, acknowledgment, and transaction semantics differ.

### 26.2. ErrorMessage does not carry the business payload

In asynchronous flows, an error handler receives an **ErrorMessage** whose payload is a Throwable, possibly referencing failedMessage. Never cast `errorMessage.getPayload()` to OrderCommand. Extract context carefully from failedMessage or a persisted inbox to retrieve eventId, tenant, and source.

### 26.3. Not every error enters the Router's default route

If a Router receives an unsupported payload type, it may route to a default/reject channel. If a Transformer throws an InvalidWireJson exception, that belongs to the **error flow**, not the Router's default route. Configure error routing separately.

### 26.4. Is an error reply needed?

- For an HTTP inbound Gateway, validation/auth errors can map to a schema-compliant HTTP response.
- For a one-way inbound Channel Adapter, you can reject/ACK/DLQ and audit per contract.
- For an outbound adapter, never fabricate a business success reply when sending fails.
- For a remote request/reply Gateway, technical errors can be translated into structured faults or exceptions per contract; a timeout is not automatically a business rejection.

### 26.5. Time-bounded quarantine with access control

An error record might look like:

~~~json
{
  "eventRef": "evt-order-901",
  "sourceType": "HTTP_PARTNER",
  "stage": "INBOUND_VALIDATION",
  "reasonCode": "EVENT_ID_HEADER_PAYLOAD_MISMATCH",
  "schemaVersion": 1,
  "outcome": "QUARANTINED"
}
~~~

Raw payloads containing PII/secrets must be encrypted or stored separately under access controls with retention and access auditing. Never dump full bodies or Authorization headers into error messages merely for debugging convenience.

### 26.6. Error taxonomy

| Error class | Example | Behavior |
| --- | --- | --- |
| **Decode** | Invalid JSON, invalid UTF-8 | Reject/quarantine |
| **Schema** | Unknown version/enum | Unsupported contract |
| **Header mapping** | Missing/wrong-type/duplicate header | Normalize/reject |
| **Trust** | Tenant spoofing, unauthorized source | Security reject |
| **Business** | Order violates policy | Typed reject if defined by contract |
| **Processing** | DB deadlock/outage | Bounded retry + recovery |
| **Outbound conversion** | Cannot encode wire v1 | Fail, alert, do not send invalid payload |
| **Transport send** | Network reset / confirm unknown | Outbox retry/reconcile |
| **Reply correlation** | Wrong requestId / late reply | Reject/park per workflow |

## 27. Security at the adapter boundary

An adapter is a **trust boundary**. Questions to answer before attaching trusted headers:

1. Who is the producer? Where does authentication proof come from?
2. Is the producer authorized to emit events for that tenant/order?
3. Does the payload exceed size/rate limits, or contain unsupported enums/types?
4. Is any header trying to steer routing/reply/error channels?
5. Has eventId already been used with a different payload?
6. Could the JSON/XML parser be abused (entity expansion, polymorphic types, excessive nesting)?
7. Could outbound replies/events leak internal metadata or another tenant's data?

### 27.1. Header injection

An external sender might send native properties matching Spring internal header names:

~~~text
trustedTenantId = tenant-admin
replyChannel = adminInternalChannel
errorChannel = suppressErrors
routingSlip = secretRoute
~~~

Never pass these names through into a Spring Message in a trusted flow. Ingress must construct trusted metadata and framework control headers strictly from internal configuration.

### 27.2. Header spoofing is not just casing

HTTP header names are case-insensitive; JMS/broker application property names follow different rules. When normalizing case, handle **duplicate/colliding header names**: for example, both `X-Event-Id` and `x-event-id` appearing with different values. Never arbitrarily pick the first or last; reject per policy.

### 27.3. Dynamic destination injection

Never treat a native header like `destination=admin.internal.queue` directly as a MessageChannel or broker destination name. Use an **allowlisted business route key** mapped through a static/trusted registry, and authorize the producer for the permitted operation.

### 27.4. Replay protection

A signed request can still be replayed. Signature verification alone does not prevent replay without an eventId/timestamp/nonce policy. Use idempotency/expiry windows and application state to protect side effects.

### 27.5. Do not use traceId as authorization

Trace IDs exist solely for observability. They can be self-asserted by external callers, altered, or shared in logs. Never use traceId as tenant identity, authorization proof, or a stable idempotency key.

### 27.6. Personal data on outbound paths

If a domain payload contains customer addresses, phone numbers, or payment metadata, outbound projection must apply **data minimization** based on what the receiver is authorized to see. Directly serializing a domain object often expands the external contract unintentionally.

## 28. Observability: tracking payload and header conversion per hop

When the same businessEventId traverses multiple adapters, total ingress/egress counts are not enough to pinpoint schema errors or dropped headers. Measure each stage separately.

### 28.1. Suggested metrics

| Metric | Meaning | Suitable labels |
| --- | --- | --- |
| **adapter_inbound_received_total** | Native messages arriving at boundary | adapterType, sourceType |
| **adapter_inbound_payload_decode_failed_total** | JSON/bytes/schema errors | adapterType, reason |
| **adapter_inbound_header_mapping_failed_total** | Missing/wrong-type/conflicting headers | adapterType, headerName allowlist |
| **adapter_inbound_auth_failed_total** | Producer/tenant unauthorized | sourceType, reason |
| **adapter_normalized_total** | Messages reaching trusted internal contract | operation, schemaVersion |
| **adapter_outbound_encoded_total** | Wire DTO successfully created | receiverType, schemaVersion |
| **adapter_outbound_send_failed_total** | Transport send errors | receiverType, reasonClass |
| **adapter_outbound_confirmed_total** | Broker/transport confirmation per contract | receiverType |
| **adapter_retries_total** | Retry attempts | direction, reasonClass |
| **adapter_duplicate_skipped_total** | Logical duplicates detected | operation |
| **adapter_id_conflict_total** | Same identity, different payload | operation |
| **adapter_quarantined_total** | Events requiring investigation | reasonCode |
| **adapter_inbound_lag_seconds** | Delay from event time to ingress | sourceType |
| **adapter_processing_duration_seconds** | Latency from ingress to outbound | operation |
| **adapter_queue_backlog** | Unprocessed work | bounded channel/queue identifier |

Never use eventId, tenantId, orderId, requestId, or traceId as **arbitrary metric labels**: high cardinality and data-leak risks apply. Use access-controlled structured logs and tracing to inspect individual events.

### 28.2. Example log on successful normalization

~~~json
{
  "component": "orderInboundMapper",
  "stage": "TRUSTED_NORMALIZATION",
  "sourceType": "HTTP_PARTNER",
  "schemaVersion": 1,
  "eventRef": "evt-order-901",
  "payloadType": "OrderCommand",
  "result": "ACCEPTED"
}
~~~

### 28.3. Log on conflicting headers

~~~json
{
  "component": "orderInboundMapper",
  "stage": "HEADER_CONSISTENCY",
  "reasonCode": "EVENT_ID_HEADER_PAYLOAD_MISMATCH",
  "sourceType": "JMS_PARTNER",
  "result": "REJECTED"
}
~~~

### 28.4. Log on outbound send

~~~json
{
  "component": "orderOutboundAdapter",
  "stage": "TRANSPORT_SEND",
  "schemaVersion": 1,
  "eventRef": "evt-order-901",
  "targetType": "AMQP",
  "result": "BROKER_ACCEPTED"
}
~~~

These are **application-defined logs**, not formats automatically generated by Spring Integration. The value `BROKER_ACCEPTED` must have a protocol-specific definition; it does not mean the receiver's business handler has finished.

### 28.5. Useful alerts

- Spike in **header mapping mismatch** rate after an API gateway/proxy deploy.
- Increase in unknown schemaVersion after a partner upgrades versions.
- Inbound accepted rising while outbound encoded stays flat.
- Outbound send retries rising while broker confirms stay flat.
- File adapter lag increasing or the same file processed multiple times.
- Abnormal jump in duplicate skipped, possibly from source redelivery or retry storms.
- DLQ/quarantine backlog sitting unowned for too long.
- Duplicate business effects after switching from DirectChannel to an async broker.
- Increasing expiration of temporary Gateway replies during high network latency.

## 29. Runbook: event has valid payload but loses headers across adapter

**Scenario:** a business handler reports missing `trustedTenantId` or `businessEventId`, even though the JSON body is valid and the external producer insists the headers were sent.

### Step 1 — Check source and security context

Identify the transport, endpoint, producer, and tenant **from authentication evidence**. Never start by "patching" `trustedTenantId` from a client HTTP header just to push processing forward.

### Step 2 — Inspect the raw wire contract selectively

~~~text
Expected:
  body.schemaVersion = 1
  body.eventId = evt-order-901
  HTTP X-Event-Id / JMS property event_id = evt-order-901

Actual:
  contentType?
  body version?
  header value type?
  duplicate header names?
~~~

Log only safe metadata; never dump Authorization headers, cookies, or customer addresses. For binary broker payloads, record hashes plus content type/schema version for investigation.

### Step 3 — Check MessageConverter

Is the message payload after the adapter **String**, **byte[]**, **File**, **OrderWireV1**, or **OrderCommand**? If the Service Activator expects OrderCommand but receives a JSON String, the bug is in payload conversion, not necessarily header mapping.

### Step 4 — Check HeaderMapper

Was native header **event_id** mapped to **businessEventId**? If HTTP `X-Event-Id` was normalized to lowercase, is code looking up the exact name specified in the contract? Is a converter/mapper dropping fields or turning a String into byte[]/List?

### Step 5 — Check the trust boundary

After authentication/authorization, did the factory/mapper attach **trustedTenantId** from VerifiedProducer? If raw x-tenant-id differs from the verified tenant, is the policy to reject or ignore/audit? Never treat the raw claim as a fallback source.

### Step 6 — Inspect Spring Message after normalization

At the boundary:

~~~text
payload class = OrderCommand
headers.trustedTenantId = tenant-a
headers.producerId = partner-a
headers.businessEventId = evt-order-901
headers.businessCorrelationKey = order:tenant-a:ORD-901:epoch-3
~~~

If this looks right, the failure happens at a later hop. If not, fix the inbound mapper, authorization, or context binding.

### Step 7 — Check Transformer/Router/HeaderFilter

A Transformer returning a new Message without copying selected headers can drop eventId. A HeaderFilter may be configured too broadly. If Splitter/Aggregator sets a technical correlationId, do not blindly overwrite the business key just to make the two match.

### Step 8 — Check outbound projection

When sending to a partner, the packet should contain only the wire body + native headers per contract, without internal `replyChannel`/`trustedTenantId`. If a receiver needs eventId and outbound omitted it, fix the **wire contract/projection** rather than serializing all Spring MessageHeaders.

### Step 9 — Check retry/ack

If the broker ACKed before side effects committed, inspect inbox/recovery state. If send confirmation was lost, use stable business IDs and idempotency to retry safely. Never generate a new UUID per send attempt.

### Step 10 — Verify after fixing

Run the tests:

1. Inbound mapper from JSON/native headers to typed payload.
2. Trusted tenant derived from authenticated context.
3. Header mismatch rejected.
4. Outbound JSON/headers contain only allowed fields.
5. Same logical retry produces no extra side effects.
6. Same ID with different payload raises ID_CONFLICT.
7. Real adapter round-trip across HTTP/JMS/AMQP/file paths.
8. Error paths and DLQ/recovery under the actual topology.

## 30. Full adapter contract test matrix

| Category | Scenario | Assertion |
| --- | --- | --- |
| **Inbound payload** | Valid JSON v1 | OrderCommand has right types/fields |
| **Inbound payload** | Schema v99 | Reject/quarantine |
| **Inbound payload** | Quantity 0 or overflow | Validation fails |
| **Inbound payload** | Unknown enum or wrong type | Contract failure |
| **Encoding** | Invalid UTF-8 / oversized body | Early rejection |
| **Inbound header** | x-event-id matches body | businessEventId is accurate |
| **Inbound header** | x-event-id differs from body | Reject mismatch |
| **Inbound header** | HTTP duplicate case variants | Reject/normalize per policy |
| **Trust** | Client claims tenant-admin, auth is tenant-a | trustedTenantId comes from auth; conflict policy applied |
| **Trust** | Unauthorized producer | Not dispatched |
| **Spring metadata** | HeaderFilter drops businessEventId | Regression test fails |
| **Transformer** | Returns new Message dropping selected headers | Caught by test |
| **Outbound payload** | Valid OrderAccepted | ACK JSON v1 has right fields |
| **Outbound header** | Selected native headers | Content-Type, x-event-id, schema-version accurate |
| **Outbound security** | Input contains replyChannel/secret | Never emitted in packet |
| **Protocol** | HTTP header name/case | Real mapper contract test |
| **Protocol** | JMS TextMessage/property | JMS converter+mapper test |
| **Protocol** | AMQP contentType/routing | AMQP converter+header test |
| **Protocol** | Truncated TCP frame | Parser does not merge wrong messages |
| **File** | Partially written file | Polling/filter skips incomplete file |
| **Retry** | Same eventId, same payload | Skips effect or replays receipt |
| **Conflict** | Same ID, different payload | ID_CONFLICT |
| **Multi-tenant** | Same orderId/eventId across tenants | Namespaces do not collide |
| **Ack** | Commit succeeds, broker ACK lost | Idempotent redelivery |
| **Crash** | Inbox RECEIVED, process restarts | Recovery processes pending item |
| **Timeout** | Outbound confirm unknown | Reconcile/bounded retry |
| **Error** | Invalid schema not retried infinitely | Quarantine |
| **Error** | Transient DB outage | Bounded retry, state retained |
| **Observability** | Mapping fails before handler | Error metric/log emitted at boundary |

### 30.1. Unit tests do not replace adapter integration tests

An `ObjectMapper.readValue(...)` test can verify JSON schema/DTOs. However, it **does not test** HTTP HeaderMapper, JMS converters, AMQP delivery tags, ACLs, ACKs, or listener container retries.

### 30.2. In-JVM integration tests do not replace network tests

OrderAdapterHarnessIntegrationTest runs DirectChannel and an in-memory sink, making it great for catching propagation bugs across endpoints. Yet it lacks real transports and process restarts. When selecting a production adapter, add tests at the real protocol boundary.

### 30.3. Testing multiple producers and versions

Run schema v1/v2, producer A/B, tenant A/B, and identical orderIds across namespaces concurrently; assert business identities never collide. If inbound is async, do not assert arrival order equals send order unless the transport/partition/ordering contract guarantees it.

## 31. Advanced hands-on: writing a custom inbound polling adapter

To distinguish a **Channel Adapter** from a test manually sending to DirectChannel, you can build a custom inbound adapter reading from a polling-capable source. Spring Integration supports **@InboundChannelAdapter** on methods supplying messages.

### 31.1. In-memory polling source

~~~java
import java.util.Objects;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;

final class DemoPollingFrameSource {
    private final BlockingQueue<TransportFrame> frames =
            new ArrayBlockingQueue<>(100);

    boolean offer(TransportFrame frame) {
        return frames.offer(Objects.requireNonNull(frame));
    }

    @InboundChannelAdapter(
            channel = "transportFrames",
            poller = @Poller(
                    fixedDelay = "1000",
                    maxMessagesPerPoll = "10"))
    public TransportFrame poll() {
        // null means there is currently no data to emit.
        return frames.poll();
    }
}
~~~

Register the `DemoPollingFrameSource` bean in a **separate test Spring context** while keeping the four channels, mappers, and handlers from OrderAdapterHarnessConfig. The poller calls `poll()`, and the adapter endpoint builds a Spring Message with a TransportFrame payload and sends it to `transportFrames`. This time, the test does not call `input.send` directly.

**Note:** this is an in-memory source, neither durable nor backed by a broker ACK. The fixedDelay poller only simulates how an inbound Channel Adapter pulls data from a source; a real JMS listener or HTTP inbound adapter has different semantics.

### 31.2. Testing polling without relying on unbounded Thread.sleep

A test can:

1. Create a Spring context with DemoPollingFrameSource.
2. Call `source.offer(frame)`.
3. Wait with a bounded timeout using polling assertions/Awaitility or a CountDownLatch at the sink.
4. Assert OutboundPacket body/headers.
5. Assert the source queue is not reprocessed unexpectedly.
6. Close the test context to stop the poller.

Never write `while(true)` loops or arbitrary `Thread.sleep` calls that hang CI. With real poller intervals, use stable timeouts and resettable test fixtures.

### 31.3. Adding an error channel for the poller

If `OrderInboundMapper` throws an exception on the poller thread, the error can travel via ErrorMessage and an error channel depending on configuration. Design:

- Safe recording of errorCode/failed eventRef.
- Retry/quarantine rules distinguishing schema errors from transient failures.
- Ensuring frames are not lost after being polled from the in-memory queue.
- With real brokers/files, selecting ACK/rename/transaction strategies suited to the connector.

**An in-memory BlockingQueue does not provide durable recovery.** If the worker crashes right after `frames.poll()` and before persistence, the frame is lost. Never use this pattern in place of a durable queue when data matters.

## 32. Exercise: swap adapters while keeping the business flow untouched

**Goal:** swap both ingress and egress endpoints **without modifying OrderProcessingActivator or DemoOrderProcessor**.

### 32.1. Three input sources

**Source A — HTTP:** receives JSON with X-Event-Id and verified credentials.

**Source B — JMS:** receives a TextMessage with event_id property, JMSMessageID, and a broker-authenticated producer.

**Source C — File/SFTP:** receives UTF-8 JSON files from a directory/account bound to a tenant in a registry.

All three must normalize into:

~~~text
Message<OrderCommand>
  payload.orderId, sku, quantity, workflowEpoch
  headers.trustedTenantId
  headers.producerId
  headers.businessEventId
  headers.businessCorrelationKey
~~~

### 32.2. Two output targets

**Target 1 — AMQP:** emits ACK JSON v1 with selected headers.

**Target 2 — File:** writes ACK into a fixed directory using a safe basename `eventId + ".ack.json"`; needs a collision/atomic-write policy so retries do not accidentally overwrite.

Never send raw MessageHeaders to the receiver. If a destination requires `businessCorrelationKey`, add that field to a **versioned wire contract** after verifying the receiver is authorized to see it, rather than opening up the full header Map.

### 32.3. Concrete tasks

1. Publish OrderWireV1 and OrderAckWireV1 schemas.
2. Define the allowlist of inbound/outbound native headers for each transport.
3. Configure authentication for HTTP/JMS/SFTP; bind VerifiedProducer from the verified source.
4. Enforce payload size, encoding, and schema validation.
5. Write the mapper from wire DTO to OrderCommand.
6. Derive trustedTenantId and correlationKey from verified context.
7. Cross-check x-event-id/event_id against body.eventId when required by the contract.
8. Reuse the exact same OrderProcessingActivator for all three sources.
9. Enforce deduplication by tenant+producer+eventId in a durable inbox.
10. Convert OrderAccepted into wire ACK per receiver schema.
11. Never emit replyChannel/errorChannel, Authorization, or internal risk fields.
12. Add schema v2 with `lineItems` and implement a v1→canonical upcaster.
13. Simulate invalid JSON, unauthorized tenants, and duplicate header casing.
14. Simulate broker redelivery after commit but before ACK.
15. Simulate lost outbound confirms and outbox publisher restarts.
16. Add tracing/metrics at each boundary.
17. Add a runbook for header mismatches and schema drift.
18. Verify end-to-end tests against real transports.

### 32.4. Acceptance criteria

| Scenario | Expected outcome |
| --- | --- |
| Valid HTTP order | Correct OrderCommand and verified tenant |
| JMS same event retried | Business effect not executed twice |
| SFTP file with out-of-scope eventId | Reject/quarantine |
| Spoofed HTTP x-tenant-id | Never becomes trustedTenantId |
| Inbound v99 body | Unsupported version, do not guess schema |
| String quantity when schema requires number | Fail or convert per published policy |
| Transformer returning new Message without eventId | Caught by integration contract test |
| Outbound AMQP ACK | Valid JSON v1 and native headers |
| Outbound File ACK | Safe filename, no path traversal |
| Two tenants same orderId | Identities/ledgers never mixed |
| Same key different payload | ID_CONFLICT |
| Lost broker confirm | Outbox retries with stable eventId |
| Rising queue backlog | Alert/backpressure |
| Callback/reply from spoofed producer | Rejected by auth |
| DLQ replay after version upgrade | Parser/upcaster handles schema correctly |

### 32.5. Architectural criteria

A business handler sees only **OrderCommand + trusted business context**, unaware of:

- Whether HTTP X-Event-Id or JMS event_id was used at the source.
- Whether the initial payload was a File, JSON String, or BytesMessage.
- Whether HeaderMapper belonged to JMS, HTTP, or AMQP.
- Whether the outbound ACK goes over AMQP or File.
- Per-attempt Spring MessageHeaders.ID or JMSMessageID.

If you have to edit business handlers whenever changing transports or source header names, the Channel Adapter boundary has failed its normalization responsibility.

## 33. Self-check questions

1. How do inbound and outbound Channel Adapters differ in data direction?
2. When is an outbound Gateway needed instead of a one-way outbound Channel Adapter?
3. Are Spring MessageHeaders identical to HTTP headers?
4. How do MessageConverter and HeaderMapper solve two different problems?
5. How do a Transformer's responsibilities differ from a Channel Adapter's?
6. Why is parsing JSON into OrderWireV1 not enough to attach trustedTenantId?
7. Should a client-asserted X-Tenant-Id ever become trustedTenantId?
8. If body.eventId differs from x-event-id, which one should be used?
9. Why might producerId and tenantId need to be part of the idempotency namespace?
10. Is MessageHeaders.ID stable across retries and redeliveries?
11. Why not copyHeaders(rawExternalHeaders) into a trusted Message?
12. Is a replyChannel header portable wire data?
13. When a handler returns a plain payload, how does Spring Integration normally handle inbound headers?
14. When a handler returns a full Message, how must header propagation be tested?
15. When a Splitter generates sequenceNumber, can it be used alone as a dedup key?
16. How does BusinessCorrelationKey differ from JMSCorrelationID and AMQP correlationId?
17. Why does a broker ACK not prove business effects committed?
18. What durability commitments must an HTTP 202 Accepted response make clear?
19. What are the pros and cons of strict ObjectMapper parsing for schema evolution?
20. Is a v2 field with different semantics from v1 but the same type and name a breaking change?
21. How does a wire DTO differ in responsibility from a domain DTO?
22. Why must internalRiskScore not be emitted in an external ACK?
23. How should OutboundPacket native headers be selected via an allowlist?
24. If an AMQP publish confirm is lost, can we conclude the message never reached the broker?
25. When an inbound file adapter reads a 2 GB file, what is safer than Files.readString?
26. Can a filename serve as authorization proof?
27. Is technical TCP connection correlation always equal to business eventId?
28. What is ErrorMessage.getPayload() typically when a handler fails?
29. Does a Router default route automatically catch exceptions from a JSON converter?
30. Why should malformed JSON not be retried infinitely like a transient DB error?
31. Does an inbox row in RECEIVED state prove side effects completed?
32. Which gap between DB and broker does transactional outbox narrow?
33. How must schema v1 messages in a DLQ be handled after consumers upgrade to v2?
34. What do inbound mapper unit tests prove that Spring context tests do not automatically imply?
35. Does a Spring context DirectChannel test prove real broker ACKs/transactions?
36. Which metrics distinguish payload decoder failures from outbound send failures?
37. Should a raw native header named routingSlip be preserved internally?
38. Why can traceId never serve as authorization proof or an idempotency key?
39. When should you move from headers to a versioned wire envelope?
40. What criterion proves an adapter successfully made the domain service transport-independent?

## 34. Pre-deployment Channel Adapter checklist

### 34.1. Inbound conversion

- Determined whether the inbound adapter is push/listener or poller, and the target channel has a clear owner.
- Published wire payload schema, version, required fields, and enums/ranges.
- Bounded message body size, encoding, parser depth, and JSON/XML deserialization policy.
- Identified payload class at every hop: byte[], String, File, wire DTO, or domain DTO.
- Configured MessageConverter for the wire format with serialize/deserialize tests.
- Normalized raw native header names/types per protocol.
- Enforced an inbound header allowlist; handled duplicate/colliding names explicitly.
- Defined consistency rules for eventId in body vs. native headers without arbitrary tie-breaking.
- Authenticated producers before building trusted context.
- Verified tenant/order ownership and publish permissions via registry/policy.
- Never used raw X-Tenant-Id or source filenames as tenant proof.
- Built trusted Spring Messages with typed domain payloads and selected headers.
- Implemented schema versioning, upcasters, and rejection policies for unknown versions.
- Rejected/quarantined malformed or untrusted inputs before business side effects.

### 34.2. Outbound conversion

- Dedicated wire reply/event DTO rather than serializing the raw domain model.
- Selected the right receiver contract version and permitted destination.
- HeaderMapper emits only allowlisted native properties.
- Stripped replyChannel, errorChannel, routingSlip, Authorization tokens, and internal fields.
- Content-Type, encoding, and schemaVersion match the actual bytes sent.
- EventId in wire body and header remain consistent per contract.
- Defined policies for send failures, unknown confirms, DLQ/retries, and outbox.
- Distinguished transport acceptance from business completion.
- Provided a Gateway or completion event/status API when a business reply is required.

### 34.3. Spring Integration topology

- MessageChannels have clear names/owners without accidentally attaching two competing consumers to a DirectChannel.
- Transformers perform appropriate conversions without silently altering business identity.
- Verified propagation of tenantId/eventId/correlation across Routers and Transformers.
- HeaderFilters do not strip business metadata still needed downstream.
- Splitter/Aggregator maintain separate technical group scopes and release policies.
- Gateway replyChannel respects the request/reply lifecycle; live channels are never serialized remotely.
- ExecutorChannel/QueueChannel/pollers have bounded capacity and appropriate error handling.
- ErrorMessage, errorChannel, and durable DLQ/quarantine are clearly separated.

### 34.4. Reliability, transactions, and retry

- BusinessEventId stays stable for the same logical event across redeliveries.
- Dedup keys are scoped to tenant/producer/operation per contract.
- Same-key/different-payload is treated as a conflict.
- Side-effecting operations use a durable inbox/idempotency ledger.
- Crash recovery handles failures between receive, persist, dispatch, and commit.
- Outbound events use an outbox or equivalent mechanism to prevent loss between DB commit and broker publication.
- Retries are bounded with backoff and classify permanent vs. transient failures.
- Unknown transport outcomes are reconciled rather than generating new operation IDs.
- File/stream adapters apply atomic read/write or appropriate rename/lock policies.
- DLQ replay is controlled for schema versions and duplicate effects.

### 34.5. Security, privacy, and observability

- Producer source, tenant, and destination are authenticated and authorized.
- External headers cannot steer arbitrary internal channels, routingSlip, or errorChannel.
- Untrusted traceRef is never used for authorization or idempotency.
- PII, tokens, and internal context are filtered/separated from outbound payloads.
- Logs record stage/reasonCode without dumping sensitive headers/bodies.
- Metric labels have bounded cardinality and protect sensitive data.
- Dashboards track inbound failures, header mismatches, outbound failures, backlogs, and retries.
- Runbooks exist for schema drift, dropped headers, and unknown ACKs.

### 34.6. Tests and deployment

- Unit tests cover wire DTOs, mappers, header allowlists, identity, and encoding.
- Unit tests verify outbound projections do not leak fields.
- Real Spring context tests exercise channels and endpoints.
- Negative tests cover header mismatches, spoofed producers, unknown schemas, and wrong types.
- Tests cover duplicates, ID_CONFLICT, multi-tenant namespaces, and timeouts.
- Adapter integration tests cover real HTTP/JMS/AMQP/TCP/File transports if used.
- Process restart/recovery tested with durable inbox/outbox.
- Version compatibility tests cover v1/v2 and DLQ replay.
- Verified converters/header mappers against the exact Spring Integration version deployed.

## 35. Conclusion

**Adapters for payload and header conversion** are about designing **a clear boundary** between external protocols and Spring Integration, not merely parsing JSON or copying a header Map.

~~~text
External system:
  Native payload + native transport headers
      |
      v
Inbound Channel Adapter:
  Authenticate source
  Decode/validate versioned wire payload
  Normalize/verify selected native metadata
  Build trusted Spring Message
      |
      v
Message<OrderCommand>:
  typed payload
  trustedTenantId / producerId
  businessEventId / businessCorrelationKey
      |
      v
Router / Transformer / Service Activator
      |
      v
Message<OrderAccepted>
      |
      v
Outbound Channel Adapter:
  Check identity and output contract
  Project to wire DTO
  Serialize payload + allowlisted native headers
  Send with retry/ack/recovery policy
      |
      v
External system
~~~

A strong design ensures **business handlers see only typed payloads and verified context**, independent of HTTP X-Event-Id, JMS properties, AMQP delivery tags, or input filenames. Simultaneously, the outbound adapter exports only data the partner is permitted to receive, preventing leaks of Spring MessageHeaders or control channels.

In systems combining Router, Filter, Transformer, Splitter, Aggregator, Messaging Gateway, retry, error channel, and correlation, test **both payloads and headers at every boundary**. Add versioning, idempotency, authorization, and observability so swapping an adapter never breaks business identity or duplicates side effects across timeouts and redeliveries.

## References

- [Enterprise Integration Patterns — Channel Adapter](https://www.enterpriseintegrationpatterns.com/patterns/messaging/ChannelAdapter.html): bridge between applications/protocols and messaging channels.
- [Enterprise Integration Patterns — Message Translator](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessageTranslator.html): converting message representations between systems.
- [Enterprise Integration Patterns — Messaging Gateway](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingGateway.html): application-side request/reply and how it differs from a one-way adapter.
- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/): overview of adapters, gateways, messaging, converters, and error handling.
- [Spring Integration Reference — Message](https://docs.spring.io/spring-integration/reference/message.html): Spring Message and MessageHeaders.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): DirectChannel, QueueChannel, ExecutorChannel, dispatch/polling semantics.
- [Spring Integration Reference — Transformer](https://docs.spring.io/spring-integration/reference/transformer.html): payload transformation and header propagation.
- [Spring Integration Reference — Service Activator](https://docs.spring.io/spring-integration/reference/service-activator.html): mapping from Message to Java method arguments.
- [Spring Integration Reference — HTTP](https://docs.spring.io/spring-integration/reference/http.html): HTTP inbound/outbound adapters, gateways, converters, and headers.
- [Spring Integration Reference — JMS](https://docs.spring.io/spring-integration/reference/jms.html): JMS adapters/gateways, header mapping, and acknowledgments.
- [Spring Integration Reference — AMQP](https://docs.spring.io/spring-integration/reference/amqp.html): AMQP adapters/gateways, properties, converters, and reply behavior.
- [Spring Integration Reference — File](https://docs.spring.io/spring-integration/reference/file.html): file adapters, filters, and outbound file handling.
- [Spring Integration Reference — SFTP](https://docs.spring.io/spring-integration/reference/sftp.html): remote file adapters and source metadata.
- [Spring Integration Reference — TCP](https://docs.spring.io/spring-integration/reference/ip.html): TCP/IP adapters, connection metadata, and serialization.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): ErrorMessage, errorChannel, and synchronous/asynchronous behavior.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): duplicate detection and idempotency advice.
- [Spring Framework — Testing](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html): Spring TestContext Framework for integration tests.

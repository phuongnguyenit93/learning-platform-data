# Correlation Across Gateways and Adapters

## 1. Context: The Same Work Crosses Multiple Communication Boundaries

In the **Content-based correlation** chapter of the **SPRING_INTEGRATION_PATTERN** module, we learn to implement Enterprise Integration Patterns with **Spring Integration** to build loosely coupled, extensible message flows. Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation can all work together in a single workflow; however, if messages traverse HTTP, JMS, AMQP, or TCP and lose their linking identity, branches can no longer assemble results accurately.

Consider a shipping quote system. A customer request might pass through:

1. An **HTTP inbound gateway** or REST controller to receive the request.
2. A **Messaging gateway** to invoke the flow like a Java method.
3. An **Outbound adapter/gateway** to send requests to carriers.
4. External brokers/HTTP services returning results.
5. An **Inbound adapter** to receive replies or event callbacks.
6. An **Aggregator** to gather three outcomes for the same request.

A flow can involve both **fast request/reply** and **asynchronous events**:

~~~mermaid
flowchart LR
    C["Client HTTP"] --> H["HTTP ingress"]
    H --> J["Java Messaging Gateway"]
    J --> G["IntegrationFlow"]
    G --> O["Outbound HTTP/JMS/AMQP"]
    O --> P["External provider"]
    P -->|"Synchronous response"| O
    P -->|"Later callback/event"| I["Inbound adapter"]
    I --> V["Verify + map correlation"]
    V --> A["Aggregator / workflow store"]
    A --> R["Business result / event"]
~~~

**Crucial question:** when a reply comes back, how does the system know which **Gateway call** it answers, which **tenant's order** it belongs to, and whether it is a **redelivery of an already-processed event**?

These three questions rely on distinct identities. Never try to solve all three by slapping the same UUID onto every header containing the word “correlation.”

### Lesson Objectives

After this lesson, you will be able to:

- Distinguish **business correlation**, **Gateway reply correlation**, and **transport/protocol correlation**.
- Know when a Gateway creates a temporary `replyChannel` and when an adapter needs a key serialized over the network.
- Establish a trustworthy correlation key at ingress and preserve it across adapters with differing header mappings.
- Use a **wire envelope** for systems that do not support forwarding Spring Message headers.
- Design request/reply flows and event-driven callbacks without equating an HTTP response with workflow completion.
- Choose timeouts, retries, idempotency, and dead-letter/recovery handling when replies arrive late or are lost.
- Write Java DSL examples and test correlation across parallel requests, different tenants, and duplicates.

## 2. Four Identifiers Often Loosely Called “Correlation ID”

| Identity | Purpose | Example | Should It Change Across a Gateway/Adapter? |
| --- | --- | --- | --- |
| **Business correlation key** | Groups events belonging to one workflow | `order-ready:v1:tenant-a:ORD-90:7` | No, within the same workflow |
| **Request/reply correlation** | Pairs a request with the reply of the current invocation | Gateway internal request token/`replyChannel` | May be unique per attempt |
| **Transport correlation** | Pairs request and response within a protocol | `JMSCorrelationID`, AMQP `correlationId`, TCP `connectionId` | Managed by the protocol adapter/gateway |
| **Event idempotency identity** | Recognizes a redelivered logical event | `tenant-a:provider-x:event-405` | Unchanged on retry of the same event |

Other metadata to keep distinct:

- **Spring `MessageHeaders.ID`**: ID of one `Message`; not a business group key.
- **`traceId`/`spanId`**: for observing requests across services; not implicitly a business key.
- **`orderId`/`requestId`**: can be components of a business key, yet insufficient across multiple tenants or workflow epochs.
- **`replyChannel`/`errorChannel`**: often in-memory objects or internal destination names; never assume they transfer intact over HTTP/JMS/TCP.
- **`ip_connectionId`**: used in Spring Integration TCP to identify a connection when sending replies via collaborating server adapters; not an order ID.

### 2.1. Example: Two HTTP Requests for the Same Order

~~~text
Business workflow:
  tenant-a / ORD-90 / epoch-7
  businessCorrelationKey = order-ready:v1:tenant-a:ORD-90:7

HTTP request A, attempt 1:
  gateway reply destination = temporary channel A
  transport request identity = req-A

HTTP request A, attempt 2 (after timeout):
  gateway reply destination = temporary channel B
  transport request identity = req-B

Business correlation key remains:
  order-ready:v1:tenant-a:ORD-90:7
~~~

If you use `replyChannel` A as the workflow key, the retry “loses” the old business state. If you replace `replyChannel` with `businessCorrelationKey`, two concurrent request/reply calls could return results to the wrong caller. **Each layer uses the exact identifier it owns.**

### 2.2. Connecting the ID Types with a Mapping Diagram

~~~mermaid
flowchart TB
    B["Business key: tenant/order/epoch"]
    B --> E1["Event A / eventId=A"]
    B --> E2["Event B / eventId=B"]
    B --> E3["Event C / eventId=C"]
    B --> R1["Gateway call attempt 1"]
    B --> R2["Gateway call attempt 2"]
    R1 --> T1["JMS/AMQP/HTTP request correlation 1"]
    R2 --> T2["JMS/AMQP/HTTP request correlation 2"]
~~~

A request/reply attempt is just **one communication exchange** in a longer workflow. For diagnostics, logs can record mappings among business key, `eventId`, `attemptId`, and transport correlation; never collapse them into one value.

## 3. How a Gateway Differs from an Adapter in Reply Contracts

In Spring Integration:

- A **Gateway** plays a request/reply role: it accepts a request and expects a reply to return to the caller or protocol peer.
- A **Channel adapter** is typically one-way: it brings messages from outside into a flow or sends messages from a flow outward, without providing a default request/reply pair.
- An **Aggregator** joins related messages; it does not automatically become an HTTP response or JMS reply unless wiring and contracts specify so.

| Endpoint | Direction | Automatically Waits for Reply? | Correlation to Watch |
| --- | --- | --- | --- |
| Messaging Gateway (Java interface) | Java call → Message → reply | Yes for non-void methods | Temporary `replyChannel`/request |
| HTTP inbound gateway | HTTP request → flow → HTTP response | Yes | HTTP call lifecycle and verified metadata |
| HTTP inbound channel adapter | HTTP request → flow | Not as request/reply | Business ID created at ingress |
| HTTP outbound gateway | Flow → remote HTTP → response | Yes | HTTP request-response, business key |
| HTTP outbound channel adapter | Flow → remote HTTP | Does not return a reply into the flow | Event ID, delivery state |
| JMS/AMQP outbound gateway | Flow → broker → reply | Yes | Protocol correlation + reply destination |
| JMS/AMQP channel adapter | One-way message into/out of broker | Does not pair request/reply | Wire envelope + business ID |
| TCP outbound gateway | TCP request → reply | Yes | Connection/request correlation |
| TCP collaborating adapters | Separate TCP send/receive | Does not pair client requests | Application correlation and connection routing |

This is a semantic table, **not** a claim that every implementation shares the same default timeout. Check exact configurations and adapter versions.

### 3.1. Synchronous vs Asynchronous Boundaries

A Java Gateway method may return a DTO synchronously while using an `ExecutorChannel` or remote service underneath; the call blocks until a reply arrives or times out.

An inbound channel adapter receiving messages from a broker may process asynchronously and publish its result to another topic minutes later. In that case, no Java caller is sitting on an old **temporary `replyChannel`**.

**Rule:** rely on `replyChannel` only when its lifetime and topology fit; for long-running workflows, use a business correlation key and durable workflow state.

## 4. How Does a Messaging Gateway Create a `replyChannel`?

A **`@MessagingGateway`** turns a Java invocation into a Spring Message. According to Spring Integration documentation, a Gateway typically creates a **temporary, anonymous, point-to-point reply channel** and sets it in the **`replyChannel`** header to route the reply back to the exact invocation.

~~~mermaid
sequenceDiagram
    participant C as Java caller
    participant G as Messaging Gateway
    participant F as IntegrationFlow
    participant S as Service Activator
    C->>G: quote(request)
    G->>F: Message + temporary replyChannel
    F->>S: handle(request)
    S-->>F: QuoteReply
    F-->>G: Message sent to replyChannel
    G-->>C: QuoteReply
~~~

Key characteristics:

1. Callers do not create a `MessageChannel` manually to receive replies.
2. The terminal handler must produce a **non-null** reply if the Gateway method expects a return value.
3. If a Filter discards the message or a handler returns `null`, the Gateway may time out waiting.
4. When a Gateway is configured with an explicit reply channel, the framework bridges to the invocation's temporary reply channel; do not assume it stops distinguishing callers.
5. Gateway-observed timeouts/exceptions must be distinguished from business errors returned by external providers.

### 4.1. A Temporary `replyChannel` Is Not a Wire-Format Field

A Spring Message may carry a `replyChannel` header holding a **`MessageChannel` object instance**. You cannot JSON-serialize that object and expect another service in a different JVM to understand it and reply to the same object.

Anti-pattern example:

~~~text
MessageHeaders:
  replyChannel = org.springframework.messaging.MessageChannel instance

Serialize all MessageHeaders to JSON and send over broker:
  replyChannel = ???  (not portable)
~~~

When crossing the network, adapters use the **protocol's reply destination** (`JMSReplyTo`/AMQP `replyTo`) or a configured **callback address / response topic** paired with a matching request token. The business correlation key should travel in a **wire envelope** or an explicitly mapped and verified header.

### 4.2. Never Use Business `correlationId` as a Channel Name

A payload may contain `orderId` or `businessCorrelationKey`, yet clients must never dictate Spring context **`replyChannel`** or **`errorChannel`** names. That is flow-control metadata; letting clients set it can cause misrouting or information leaks.

When replying to a client, use an allowlisted destination/route or look it up from an internal registry, enforce authorization, and never dynamically create channels from raw input strings.

## 5. Correlation Strategy at Entry Points

**Content-based correlation** derives the key from **trusted business data** (payload, registry records, or verified metadata), instead of taking a random `MessageHeaders.ID`.

Example rule:

~~~text
businessCorrelationKey =
    "shipment-quote:v1:"
    + verifiedTenantId + ":"
    + normalizedShipmentId + ":"
    + workflowEpoch
~~~

Same tenant + shipment + epoch → same key, whether traversing an HTTP Gateway, JMS adapter, or a replay.

### 5.1. Preventing Two Opposite Failures

| Failure | Cause | Consequence |
| --- | --- | --- |
| **False split** | Same workflow, yet each adapter creates a fresh UUID | Aggregator splits into multiple incomplete groups |
| **False join** | Two different tenants/epochs share the same `shipmentId` | Merges data across wrong customers or versions |

To prevent both, ensure:

- Tenant comes from verified security principal/ACLs.
- Shipment/Order ID is canonicalized per contract.
- Workflow epoch is looked up by logical workflow, never incremented per attempt.
- A consistent schema/key version across all ingress points.
- Header mappings/wire envelopes preserve identity across adapter hops.
- Cross-protocol and cross-tenant tests exist.

### 5.2. Do Not Blindly Trust a Header Named `X-Correlation-ID`

A client might send:

~~~http
POST /api/shipments/SHIP-901/quotes HTTP/1.1
X-Tenant-Id: tenant-admin
X-Correlation-ID: tenant-admin:SHIP-999:7
Content-Type: application/json

{"shipmentId":"SHIP-901","epoch":7}
~~~

Never convert raw **`X-Tenant-Id`** and **`X-Correlation-ID`** into the framework's `trustedTenantId`/`businessCorrelationKey`. Verify the token, bindings, and access rights, then compute or look up the internal business key yourself.

If you need to store a client-provided trace token, validate its length/charset and place it in a dedicated tracking header/log—**never** use it as an Aggregator key or authorization mechanism.

## 6. Java 17: Model with Explicit Identity and Response

We use an **internal quoting** example to isolate the Gateway mechanism without calling external services or writing to a database. Later sections add transport adapters.

~~~java
import java.math.BigDecimal;

record QuoteCommand(
        String shipmentId,
        int workflowEpoch,
        int packageCount) {
    QuoteCommand {
        if (shipmentId == null
                || !shipmentId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("INVALID_SHIPMENT_ID");
        }
        if (workflowEpoch < 1 || packageCount < 1
                || packageCount > 1000) {
            throw new IllegalArgumentException("INVALID_QUOTE_INPUT");
        }
    }
}

record QuoteReceipt(
        String businessCorrelationKey,
        String shipmentId,
        BigDecimal amountVnd,
        String status) {
}
~~~

**`QuoteCommand` does not contain a client-claimed tenant.** Tenant comes from the verified security context and is passed through an application service layer, never inferred from the request body.

### 6.1. Pure Business Key Builder

~~~java
final class QuoteCorrelation {
    private static final String PREFIX = "shipment-quote:v1:";
    private QuoteCorrelation() {}

    static String key(
            String verifiedTenantId,
            QuoteCommand command) {
        if (verifiedTenantId == null
                || !verifiedTenantId.matches("[a-z0-9_-]{1,48}")) {
            throw new IllegalArgumentException("INVALID_VERIFIED_TENANT");
        }
        return PREFIX + verifiedTenantId
                + ":" + command.shipmentId()
                + ":" + command.workflowEpoch();
    }
}
~~~

This is an **illustrative rule**: tenant uses `a-z`, `shipmentId` allows alphanumeric/hyphen/underscore, and epoch is positive. In other domains, if shipment IDs allow Unicode or delimiters, use unambiguous canonical encoding; if case normalization is forbidden, never auto-uppercase or lowercase.

### 6.2. Application Service Enforcing the Tenant Boundary

~~~java
record VerifiedCaller(String principalId, String tenantId) {}

interface ShipmentAccessPolicy {
    void assertCanRequestQuote(
            VerifiedCaller caller,
            QuoteCommand command);
}

final class QuoteApplicationService {
    private final ShipmentAccessPolicy access;
    private final QuoteGateway gateway;

    QuoteApplicationService(
            ShipmentAccessPolicy access,
            QuoteGateway gateway) {
        this.access = access;
        this.gateway = gateway;
    }

    QuoteReceipt requestQuote(
            VerifiedCaller caller,
            QuoteCommand command) {
        access.assertCanRequestQuote(caller, command);
        String key = QuoteCorrelation.key(caller.tenantId(), command);
        return gateway.quote(command, key);
    }
}
~~~

In production, **`ShipmentAccessPolicy`** must verify that the shipment belongs to the tenant and `workflowEpoch` matches an authorized instance. If callers could pick arbitrary epochs, the same shipment could be falsely split across groups. This example assumes the policy verifies that before invoking the Gateway.

## 7. Messaging Gateway: Passing the Business Key Without Hijacking `replyChannel`

A gateway interface lets business code invoke a Java method while the framework manages the request message and reply destination.

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@MessagingGateway
interface QuoteGateway {
    @Gateway(requestChannel = "quoteGatewayRequests")
    QuoteReceipt quote(
            @Payload QuoteCommand command,
            @Header("businessCorrelationKey") String groupKey);
}
~~~

**`@Header` in this example receives the key from the verified `QuoteApplicationService`**, not a header controlled directly by a client. Never let external APIs call a gateway method with an arbitrary `groupKey` without passing through policy checks.

### 7.1. Java DSL Flow Returning a Synchronous Reply

~~~java
import java.math.BigDecimal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
@IntegrationComponentScan
class QuoteGatewayFlowConfig {
    @Bean
    MessageChannel quoteGatewayRequests() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow quoteGatewayFlow() {
        return IntegrationFlow.from("quoteGatewayRequests")
                .handle(QuoteCommand.class, (command, headers) -> {
                    Object rawKey = headers.get(
                            "businessCorrelationKey");
                    if (!(rawKey instanceof String key)
                            || key.isBlank()) {
                        throw new IllegalArgumentException(
                                "MISSING_BUSINESS_CORRELATION_KEY");
                    }

                    BigDecimal price =
                            BigDecimal.valueOf(75_000L)
                                    .multiply(BigDecimal.valueOf(
                                            command.packageCount()));

                    return new QuoteReceipt(
                            key,
                            command.shipmentId(),
                            price,
                            "QUOTED");
                })
                .get();
    }
}
~~~

The final `.handle()` endpoint returns a **non-null `QuoteReceipt`** payload. Because the flow configures no fixed `outputChannel` and the request carries the Gateway's `replyChannel`, the framework sends the reply back to that destination. This is a request/reply example **inside the same Spring context**; it does not prove transport headers pass through HTTP/JMS/TCP without configuring a mapper.

### 7.2. What Does the Gateway Do When There Is No Reply?

If the handler returns `null` or a Filter drops the request, the caller may:

- Wait until the configured **reply timeout** elapses.
- Receive `null` or an exception depending on Gateway method signature/config/version; test the contract.
- Never conclude an external service did not execute a side effect merely from the absence of a reply.

Never declare a Gateway method returning `QuoteReceipt` and intentionally call a one-way Service Activator expecting a reply to appear on its own.

Set bounded timeouts matching SLAs. If a request can run for hours, use **async accepted + workflow status** rather than blocking Java/HTTP threads until every event arrives.

### 7.3. A Void Gateway Method

For one-way communication, a method can be declared `void`. Per Spring Integration documentation, for void gateway methods (since Spring Integration 5.4), when no `replyChannel` is provided, the framework may set `replyChannel` to `nullChannel` to discard unnecessary replies.

This **does not mean side effects have finished** when the method returns, especially with async downstream flows; nor does it turn a one-way flow into a correlation mechanism for subsequent events.

## 8. Sending Requests Through an Adapter: What Survives?

When crossing the network, a Spring Message is mapped to the protocol's representation:

~~~text
Spring Message:
  payload=QuoteCommand
  headers:
    businessCorrelationKey=shipment-quote:v1:tenant-a:SHIP-901:7
    replyChannel=<temporary Java MessageChannel>
    id=<spring-message-id>

Network message:
  body=<serialized representation>
  protocol properties=<allowed mapped headers>
  reply destination=<JMSReplyTo / AMQP replyTo / HTTP response context>
~~~

**There is no universal rule that all Spring headers pass through all adapters.** Each transport has its own `HeaderMapper`, `MessageConverter`, serializer/framing, and configuration. Many transports send only the payload unless configured to map headers.

### 8.1. Minimum Data That Must Cross the Wire for Callbacks

A remote reply or event callback needs:

- **`businessCorrelationKey`** or sufficient components to **re-derive/look up** the key.
- **`eventId`** or `operationId` for deduplication.
- **`producerId`/`supplierId`/`partKind`** when a group gathers from multiple sources.
- **`schemaVersion`** to parse the payload properly.
- **Business status/result** so we know whether the member has reached a terminal state.

If request/reply must route a response back to a waiting caller, you also need a **transport request token or reply destination** per protocol rules. This token differs from the business group key and does not replace it.

### 8.2. Never Unconditionally Serialize Internal Spring Messages

A call like:

~~~java
objectMapper.writeValueAsString(message.getHeaders());
~~~

is not a stable cross-system protocol. Headers can hold non-serializable objects such as `replyChannel`/`errorChannel`, Java classes, or internal metadata. Design an explicit, versioned **wire DTO/envelope** with well-defined fields.

## 9. Wire Envelope: A Portable Way to Carry Content-Based Keys

A JSON wire structure usable consistently across HTTP, brokers, or TCP:

~~~json
{
  "schemaVersion": 1,
  "businessCorrelationKey": "shipment-quote:v1:tenant-a:SHIP-901:7",
  "eventId": "evt-provider-778",
  "providerId": "PARTNER-A",
  "shipmentId": "SHIP-901",
  "workflowEpoch": 7,
  "result": {
    "status": "QUOTED",
    "totalVnd": "150000"
  }
}
~~~

This is an **application wire format**, not Spring Integration auto-mapping. Define fields and JSON schema versions so both sides agree:

- **`businessCorrelationKey`** is the group identity **issued internally**, not proof of authorization.
- **`eventId`** stays unchanged across retries/redeliveries of the same result.
- **`providerId`** identifies the reply source and prevents double-counting one supplier.
- **`shipmentId`/epoch** verify the key and domain identity match.
- **`totalVnd`** is a decimal string to avoid floating-point rounding errors; validate scale and currency.

An external service may supply only fields permitted by the contract. At ingress, never trust tenant/role just because they appear in JSON; authenticate the source via mTLS/OAuth/broker ACLs and look up authorized business mappings.

### 9.1. Guarding Against Tampering and Replays

If a callback contains a `businessCorrelationKey` in its body yet comes from an unauthorized sender, it must not join the group merely because the key is syntactically valid. Inbound pipeline:

1. Authenticate producer identity.
2. Check whether the producer is authorized to emit this **`providerId`/`partKind`**.
3. Validate `schemaVersion`, field lengths, enums, and signatures if required by contract.
4. Look up the persisted shipment/workflow binding and verify `shipmentId`, epoch, and tenant.
5. Recompute or look up the **expected `businessCorrelationKey`**; reject mismatches.
6. Check whether `eventId` was already processed and whether the payload digest matches any prior arrival.
7. Only then construct a **fresh internal Spring Message** to send to the Aggregator/flow.

Never copy wire headers such as `replyChannel`, `errorChannel`, or `routingSlip` into a Spring Message if they originate outside the trust boundary.

### 9.2. Java Records as the Wire Contract

~~~java
import java.math.BigDecimal;

record QuoteResultWire(
        int schemaVersion,
        String businessCorrelationKey,
        String eventId,
        String providerId,
        String shipmentId,
        int workflowEpoch,
        String status,
        String totalVnd) {}

record VerifiedTransportPeer(
        String authenticatedPeerId,
        String tenantId) {}

record VerifiedQuoteResult(
        String businessCorrelationKey,
        String eventId,
        String providerId,
        String shipmentId,
        int workflowEpoch,
        String tenantId,
        String status,
        BigDecimal totalVnd) {}
~~~

These records are example DTOs; adapter parsers/deserializers must enforce input sizes and schemas before building `VerifiedQuoteResult`. Never treat a record constructor as authentication.

### 9.3. Writing an Inbound Mapper That Verifies Correlation

~~~java
import java.math.BigDecimal;
import java.util.Set;

interface QuoteWorkflowRegistry {
    boolean isActiveOrRecoverable(
            String tenantId, String shipmentId, int epoch);

    boolean mayReport(
            String authenticatedPeerId, String providerId);
}

final class QuoteWireVerifier {
    private final QuoteWorkflowRegistry registry;

    QuoteWireVerifier(QuoteWorkflowRegistry registry) {
        this.registry = registry;
    }

    VerifiedQuoteResult verify(
            QuoteResultWire wire,
            VerifiedTransportPeer peer) {

        if (wire == null || peer == null
                || wire.schemaVersion() != 1
                || wire.eventId() == null
                || !wire.eventId().matches("[A-Za-z0-9_-]{1,80}")
                || wire.providerId() == null
                || !Set.of("PARTNER-A", "PARTNER-B", "BACKUP")
                        .contains(wire.providerId())) {
            throw new IllegalArgumentException("INVALID_WIRE_EVENT");
        }

        if (!registry.mayReport(
                peer.authenticatedPeerId(), wire.providerId())) {
            throw new SecurityException("PROVIDER_NOT_AUTHORIZED");
        }

        QuoteCommand identity = new QuoteCommand(
                wire.shipmentId(), wire.workflowEpoch(), 1);
        if (!registry.isActiveOrRecoverable(
                peer.tenantId(), identity.shipmentId(),
                identity.workflowEpoch())) {
            throw new SecurityException("WORKFLOW_NOT_AUTHORIZED");
        }

        String expected = QuoteCorrelation.key(
                peer.tenantId(), identity);
        if (!expected.equals(wire.businessCorrelationKey())) {
            throw new SecurityException("CORRELATION_MISMATCH");
        }

        if (!"QUOTED".equals(wire.status())
                && !"UNAVAILABLE".equals(wire.status())) {
            throw new IllegalArgumentException("UNKNOWN_STATUS");
        }

        BigDecimal price = null;
        if ("QUOTED".equals(wire.status())) {
            try {
                price = new BigDecimal(wire.totalVnd());
            } catch (NumberFormatException | NullPointerException ex) {
                throw new IllegalArgumentException(
                        "INVALID_QUOTE_AMOUNT", ex);
            }
            if (price.signum() <= 0 || price.scale() > 0) {
                throw new IllegalArgumentException("INVALID_QUOTE_AMOUNT");
            }
        } else if (wire.totalVnd() != null) {
            throw new IllegalArgumentException("UNAVAILABLE_WITH_PRICE");
        }

        return new VerifiedQuoteResult(
                expected,
                wire.eventId(),
                wire.providerId(),
                identity.shipmentId(),
                identity.workflowEpoch(),
                peer.tenantId(),
                wire.status(),
                price);
    }
}
~~~

**Key point:** the mapper recomputes the expected key from the **authenticated peer identity** and workflow registry. It never lets the remote producer pick the group. `price` is parsed only when `QUOTED`; for `UNAVAILABLE`, the outcome can still go to the Aggregator as **a typed terminal outcome**.

**Example limitations:** production also needs verified peer→tenant mapping, rate limits, distinguishing timeouts/UNKNOWN from `UNAVAILABLE`, currency checks, timestamps/signatures, and protection against duplicate `eventId`s with different payloads. Registry lookups may need transactional semantics; this snippet does not perform full authentication on its own.

### 9.4. Rebuilding the Spring Message from the Verified DTO

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class QuoteMessageMapper {
    static Message<VerifiedQuoteResult> internal(
            VerifiedQuoteResult result) {
        return MessageBuilder.withPayload(result)
                .setHeader(
                        "businessCorrelationKey",
                        result.businessCorrelationKey())
                .setHeader(
                        "trustedTenantId",
                        result.tenantId())
                .setHeader(
                        "businessEventId",
                        result.eventId())
                .setHeader(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        result.businessCorrelationKey())
                .build();
    }
}
~~~

The rebuilt inbound message gets a new Spring `MessageHeaders.ID`, while **`businessCorrelationKey` and `eventId` stay intact**. Never copy a `replyChannel` from a wire body or HTTP header. This cleanly separates **wire metadata** from **framework routing metadata**.

### 9.5. Why Is `schemaVersion` Necessary?

If a provider upgrades from version 1 to version 2 and silently renames `shipmentId`, mappers can fail to extract the right identity. For correlation, **silent fallback** from a missing `shipmentId` to a random ID is dangerous: it fragments a real group into bogus groups.

Reject/quarantine unsupported schemas or maintain versioned converters with compatibility tests. If key construction algorithms change, version the keys and plan to drain/migrate open groups.

## 10. HTTP: Request-Response Transport Differs from Business Callbacks

HTTP binds one request to one response on the same HTTP call. If an application simply sends a quote request and gets an immediate response, an **HTTP outbound gateway** models that request/reply without inventing a new HTTP header to remind the framework which socket is waiting.

However, when a remote service **returns 202 Accepted** and calls back minutes later, the original HTTP exchange is over. The callback is **a separate HTTP request** and cannot automatically return to the old Gateway's temporary `replyChannel`.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Application
    participant P as Provider
    participant S as Workflow Store
    C->>A: POST /quote-requests
    A->>S: Persist businessCorrelationKey + state
    A->>P: POST /provider/quotes + business operation ID
    P-->>A: HTTP 202 Accepted
    A-->>C: HTTP 202 + trackingId
    Note over C,A: First HTTP request/reply has ended
    P->>A: POST /callbacks with eventId and group key
    A->>S: Verify provider + dedup + correlate
    A-->>P: HTTP 2xx once callback is durably accepted
    A->>S: Aggregate / complete workflow
~~~

### 10.1. HTTP `HeaderMapper` Can Drop Custom Headers

Spring Integration uses an HTTP `HeaderMapper` and provides settings to control which request/response headers are mapped. Per the documentation, **standard HTTP headers** have default mappings; when specifying custom header patterns, check whether desired standard headers remain included.

Never assume a custom Spring header named `businessCorrelationKey` will automatically arrive at the peer as `X-Business-Correlation-Key`, nor that a remote HTTP header automatically becomes a trusted Spring Message header.

An XML example selecting outbound headers:

~~~xml
<!-- Configuration snippet assuming int-http namespace
     and appropriate channel/connection beans are declared. -->
<int-http:outbound-gateway
    id="remoteQuoteHttpGateway"
    url="https://provider.example/quotes"
    request-channel="remoteQuoteHttpRequests"
    reply-channel="remoteQuoteHttpReplies"
    mapped-request-headers="X-Operation-Id, X-Trace-Id, HTTP_REQUEST_HEADERS"
    mapped-response-headers="HTTP_RESPONSE_HEADERS" />
~~~

This is **illustrative syntax for `HeaderMapper`**, not a complete production TLS/HTTP client configuration. Never send sensitive security data in custom headers, and never trust response headers from a remote service without verifying origin.

### 10.2. Put Business IDs in the Body or Headers?

| Option | Best When | Notes |
| --- | --- | --- |
| **Body / wire envelope** | Callbacks/broker events are business data | Versioned contract; validate thoroughly |
| **HTTP header** | Tracing/routing among trusted services | Proxies/gateways may rewrite or unmapped headers drop |
| **Both body and header** | Fast inspection plus durable domain correlation | Assert both values match; never pick silently |

A **business correlation key in the body** keeps data meaningful after persisting events or replaying from a DLQ. Additional HTTP headers can assist tracing without replacing authenticated business content.

### 10.3. Do Not Mistake HTTP 200 for Aggregate Completion

An HTTP outbound gateway receiving `200 OK` means the remote HTTP endpoint succeeded under its own contract. That may mean only **request accepted**, not that all three suppliers emitted outcomes or booking finished.

Distinguish states clearly:

~~~text
HTTP_RECEIVED
REMOTE_ACCEPTED
WORKFLOW_IN_PROGRESS
WORKFLOW_COMPLETED
WORKFLOW_FAILED
WORKFLOW_UNKNOWN
~~~

Store exact states in the workflow state store and status API. Never emit a `COMPLETED` business event solely because sending a request via an adapter threw no error.

## 11. JMS: `JMSCorrelationID` and `JMSReplyTo` Are Request/Reply Protocol Metadata

A JMS outbound gateway sends a request message to a **request destination** and awaits a reply from a **reply destination**. Per Spring Integration JMS documentation, if no `correlation-key` attribute is set, the gateway typically expects the response's `JMSCorrelationID` to match the **outbound request's `JMSMessageID`**. When `correlation-key` is configured, the gateway can generate its own correlation token and expect the responder to echo that token in the same property/header.

~~~text
JMS request:
  JMSMessageID = ID:broker-391
  JMSReplyTo   = queue.reply.temporary
  businessCorrelationKey = shipment-quote:v1:tenant-a:SHIP-901:7

JMS reply:
  JMSCorrelationID = ID:broker-391
  body = provider response
~~~

`JMSCorrelationID` in this example pairs **one JMS request and one JMS reply**; it is not necessarily the key the Aggregator uses to combine business results from multiple suppliers. Even if configuration happens to give both strings the same content, they still serve **two distinct responsibilities**.

### 11.1. Do Not Blindly Overwrite `JMSCorrelationID`

Spring Integration JMS supports multiple `correlation-key` and reply-listener modes, such as passing through `JMSCorrelationID` or a custom property. Some modes permit pre-existing IDs, while others are **incompatible** with a reply listener because they require uniqueness or specific selectors.

**Rule:** when using a reply-managing Outbound Gateway, let the Gateway and responder follow the agreed protocol correlation. Never set `JMSCorrelationID = orderId` across concurrent requests without checking semantics and uniqueness; replies could mis-match callers or break selectors.

### 11.2. One-Way JMS Channel Adapters Do Not Auto-Correlate Request/Reply

With two independent adapters:

~~~text
JMS outbound adapter -> queue.request
Remote worker        -> queue.response
JMS inbound adapter  -> application
~~~

There is no automatic **temporary Gateway `replyChannel`** bridging both sides. The application must carry request identity over the wire (`businessCorrelationKey`, `eventId`, `operationId`) and place **correlation logic** in inbound/recovery/aggregator layers. Use response topics with appropriate partition/routing keys, an inbox/dedup store, and TTLs.

### 11.3. Mappers and Converters Must Match the Contract

Spring Integration JMS supports **`HeaderMapper`** to translate Spring Message headers to JMS properties/headers and back. Never assume arbitrary Java object headers convert into JMS properties. Use wire-compatible primitives (String, numbers, Boolean, etc.) alongside a versioned DTO/JSON body for business data.

When using JMS `ReplyTo`/correlation for a sync gateway, **never serialize a Java `replyChannel` object** over the broker. That is not how JMS gateways manage replies.

## 12. AMQP: RPC `replyTo`/Correlation Differs from Business Groups

Spring Integration AMQP offers both **one-way channel adapters** and **request/reply inbound/outbound gateways**. With RabbitMQ, RPC typically relies on protocol properties such as `replyTo` and `correlationId`, managed by Spring AMQP/Integration adapters.

~~~mermaid
sequenceDiagram
    participant A as App A
    participant B as AMQP Broker
    participant S as Service B
    A->>B: Request + replyTo + AMQP correlation
    B->>S: Deliver request
    S->>B: Reply + matching correlation
    B-->>A: Deliver reply
    Note over A: Gateway matches reply to waiting request
~~~

The **business correlation key** can travel as an allowlisted AMQP header or inside the body. When events from multiple services belong to one workflow, the business key is what groups them in the Aggregator.

### 12.1. Two Non-Equivalent AMQP Patterns

- **Outbound Gateway**: suits RPC contracts needing a single reply within a reply deadline; the adapter manages AMQP request/reply matching.
- **Outbound Adapter + Inbound Adapter**: suits asynchronous event exchange, late callbacks, multiple replies, or multiple workers; the application must supply its own correlation, idempotency, and workflow state.

If remote processing exceeds the reply timeout, a sync gateway cannot meaningfully “wait for the final outcome” merely by cranking timeouts up indefinitely. Use event-driven replies and a workflow store for long-term resilience.

### 12.2. `HeaderMapper` and Producer Trust

AMQP headers can be set by producers; broker ACLs/mTLS verify **connection identity**, yet do not automatically make every business field in the payload trustworthy. At inbound:

1. Verify source and routing permissions.
2. Deserialize under the expected schema.
3. Compute or look up the business key from trusted tenant/workflow state.
4. Compare the accompanying business key against the expected key.
5. Build a fresh internal Spring Message and strip unauthorized control headers.

Never accept arbitrary `routingSlip`, `errorChannel`, or `replyChannel` headers from an AMQP message crossing a trust boundary.

## 13. TCP: Gateways Have Correlation; Collaborating Adapters Need Application Logic

Per Spring Integration **TCP Message Correlation** documentation:

- TCP Gateways support matching request/reply correlation.
- Over a single shared connection, an outbound gateway may be limited to one active request/reply at a time on that connection; evaluate throughput against your connection factory configuration.
- With collaborating inbound/outbound adapters on the client side, **application correlation generally must be implemented yourself**.
- On the server side, the TCP inbound adapter attaches **`ip_connectionId`** so the outbound adapter knows which TCP connection receives the reply.
- TCP defaults typically transfer only the **payload**; transferring headers requires configuring appropriate mappers and serializers.

### 13.1. `ip_connectionId` Does Not Replace Order `correlationId`

~~~text
TCP connection ip_connectionId = conn-10
  request A: shipment SHIP-901 / epoch 7
  request B: shipment SHIP-902 / epoch 1

Both A and B travel on conn-10:
  ip_connectionId is identical
  businessCorrelationKey differs
~~~

One connection can carry many logical requests; multiple connections can carry retries of the same business workflow. Thus `ip_connectionId` is neither a business group key nor an `eventId`.

### 13.2. TCP Header Transfer Requires Explicit Configuration

TCP documentation explains using **`MessageConvertingTcpMessageMapper`** and serializers/deserializers to transfer selected headers alongside payloads, choosing `correlationId`, `sequenceNumber`, `sequenceSize`, or custom business headers as needed.

Many TCP configurations default to sending only the payload. **Never** construct a message at the receiver expecting all sender Spring `MessageHeaders` to appear automatically.

In polyglot environments, a JSON/protobuf wire envelope carrying `businessCorrelationKey` is generally easier to govern than serialized Java `Message` objects.

### 13.3. TCP Half-Close, Timeouts, and Late Replies

A request may reach the server while the connection drops before the reply returns. Caller timeout **does not prove the server had no side effect**. When retrying over another connection:

- Keep the business operation ID stable.
- Have the server enforce idempotency/status lookups.
- If a reply from an old attempt arrives late, never misattribute it to the new attempt.
- With asynchronous TCP adapters, maintain a request→response mapping store rather than relying solely on `connectionId`.

## 14. File/SFTP/Email Adapters Have No Built-In Request/Reply Correlation

A file or email inbound adapter creates messages from files, emails, or poll events. Filenames, modification times, or email `Message-ID`s help identify origin, yet **do not automatically form business group IDs**.

For example, an import batch split across multiple files:

~~~text
import-APR-10-part-1.csv
import-APR-10-part-2.csv
import-APR-10-part-3.csv
~~~

The application must validate the batch manifest, expected count, tenant, and version, then derive `businessCorrelationKey` from the **batch identity**. Never group arbitrary files sharing a user-chosen prefix without verifying the file belongs to an authorized batch and tenant.

Moving or renaming a file after reading does not guarantee data committed. If a file is re-scanned after a crash, use file checksums/`eventId`/an inbox to prevent duplicate side effects and avoid spawning a bogus new group.

## 15. Multiple Callbacks in One Workflow: Which Key Does the Aggregator Use?

Suppose a quote request expects **three providers** to reply via different inbound adapters:

~~~text
PARTNER-A -> HTTP callback -> VerifiedQuoteResult
PARTNER-B -> JMS inbound   -> VerifiedQuoteResult
BACKUP    -> AMQP inbound  -> VerifiedQuoteResult
~~~

All three messages must carry the **same `businessCorrelationKey`**. Yet their **`eventId`, `providerId`, and transport correlation IDs** differ. An internal Aggregator can group by the verified `businessCorrelationKey`.

### 15.1. Group Completion Differs from Message Count

Three messages all from `PARTNER-A` do not satisfy three suppliers. `ReleaseStrategy` must verify the expected set of providers:

~~~text
expected = {PARTNER-A, PARTNER-B, BACKUP}
received = {PARTNER-A, PARTNER-B, BACKUP}
=> complete

received = {PARTNER-A, PARTNER-A, BACKUP}
=> NOT complete, even though 3 messages were received
~~~

With redeliveries, handle duplicates **before the Aggregator**. If a duplicate pushes the group to four messages, a release strategy checking `size==3` can stall forever; never switch to `size>=3` as that masks duplicates and collisions.

### 15.2. Java DSL Grouping Callbacks by Content-Based Key

~~~java
import java.util.Set;
import java.util.HashSet;
import org.springframework.integration.store.MessageGroup;

final class QuoteGroupRules {
    static final Set<String> EXPECTED =
            Set.of("PARTNER-A", "PARTNER-B", "BACKUP");

    private QuoteGroupRules() {}

    static boolean complete(MessageGroup group) {
        if (group.size() != EXPECTED.size()) {
            return false;
        }

        Set<String> providers = new HashSet<>();
        for (var message : group.getMessages()) {
            if (!(message.getPayload()
                    instanceof VerifiedQuoteResult result)) {
                return false;
            }
            if (!EXPECTED.contains(result.providerId())
                    || !providers.add(result.providerId())) {
                return false;
            }
        }
        return providers.equals(EXPECTED);
    }
}
~~~

An illustrative `IntegrationFlow`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class QuoteCallbackFlowConfig {

    @Bean
    MessageChannel verifiedQuoteCallbacks() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel quoteAggregationOutput() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow callbackAggregationFlow() {
        return IntegrationFlow.from("verifiedQuoteCallbacks")
                .aggregate(a -> a
                        .correlationStrategy(message -> {
                            Object value = message.getHeaders()
                                    .get("businessCorrelationKey");
                            if (!(value instanceof String key)
                                    || key.isBlank()) {
                                throw new IllegalArgumentException(
                                        "MISSING_CORRELATION_KEY");
                            }
                            return key;
                        })
                        .releaseStrategy(QuoteGroupRules::complete)
                        .outputProcessor(QuoteReports::fromGroup)
                        .groupTimeout(30_000)
                        .sendPartialResultOnExpiry(false))
                .channel("quoteAggregationOutput")
                .get();
    }
}
~~~

**Important:** the `verifiedQuoteCallbacks` input **accepts only messages already passed through `QuoteWireVerifier`**. An HTTP callback must never send unauthenticated payloads straight to the aggregator. This configuration is **illustrative inside one Spring context**, without a persistent `MessageGroupStore`, inbox, multi-instance locking, or real business deadline.

### 15.3. Building the Report When All Three Sources Arrive

~~~java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.List;

import org.springframework.integration.store.MessageGroup;

record QuoteAggregationReport(
        String businessCorrelationKey,
        int receivedCount,
        String status,
        VerifiedQuoteResult bestQuote,
        List<VerifiedQuoteResult> outcomes) {}

final class QuoteReports {
    private QuoteReports() {}

    static QuoteAggregationReport fromGroup(MessageGroup group) {
        if (!QuoteGroupRules.complete(group)) {
            throw new IllegalStateException("INCOMPLETE_QUOTE_GROUP");
        }

        List<VerifiedQuoteResult> outcomes = group.getMessages().stream()
                .map(message ->
                        (VerifiedQuoteResult) message.getPayload())
                .sorted(Comparator.comparing(
                        VerifiedQuoteResult::providerId))
                .toList();

        String key = outcomes.get(0).businessCorrelationKey();
        String tenant = outcomes.get(0).tenantId();
        for (VerifiedQuoteResult item : outcomes) {
            if (!key.equals(item.businessCorrelationKey())
                    || !tenant.equals(item.tenantId())) {
                throw new IllegalStateException(
                        "MIXED_CORRELATION_OR_TENANT");
            }
        }

        VerifiedQuoteResult best = outcomes.stream()
                .filter(item -> "QUOTED".equals(item.status()))
                .min(Comparator.comparing(
                        VerifiedQuoteResult::totalVnd))
                .orElse(null);

        return new QuoteAggregationReport(
                key,
                outcomes.size(),
                best == null ? "NO_OFFER"
                        : outcomes.stream().allMatch(item ->
                                "QUOTED".equals(item.status()))
                                ? "COMPLETE"
                                : "PARTIAL_SUPPLIER_FAILURE",
                best,
                List.copyOf(outcomes));
    }
}
~~~

**Example limitation:** the report proves only that three **terminal outcomes** entered the active group; it does not mean all three suppliers committed in the same transaction. If every supplier is `UNAVAILABLE`, `bestQuote=null` is valid, yet `reportStatus` must be `NO_OFFER`, not `COMPLETE`.

### 15.4. Correlation for Splitter Sub-Groups

When a flow splits a batch via a Splitter and queries three providers for **each item**, there are at least two levels of correlation:

~~~text
batch = B-100
  item 1 -> provider replies (PARTNER-A/B/BACKUP)
  item 2 -> provider replies (PARTNER-A/B/BACKUP)
  item 3 -> provider replies (PARTNER-A/B/BACKUP)
~~~

If only `batchId` is used as the key, all 9 supplier replies merge into one group instead of three subgroups. You need a key at the level **`batchId + itemId + workflowEpoch`** for provider results, and a parent Aggregator gathering item summaries by batch key. Never blindly copy `CORRELATION_ID` from a Splitter without verifying group semantics.

## 16. Timeouts: Gateway, Adapter, and Aggregator Have Different Clocks

An application can configure **four timeout boundaries** for the same workflow:

| Timeout | Where Applied | What Happens on Expiry |
| --- | --- | --- |
| **Gateway reply timeout** | Java request/reply call | Caller stops waiting for a reply |
| **Transport timeout** | HTTP/JMS/AMQP/TCP | Communication attempt may fail or drop connection |
| **Aggregator `groupTimeout`** | Message group in `MessageGroupStore` | Incomplete group follows expiry policy |
| **Business deadline** | Persistent workflow state | Workflow transitions to `INCOMPLETE`/`FAILED`/`RECONCILING` |

Never set all four to 5 seconds expecting the system to stay consistent. An external provider could:

1. Receive the request and complete business work at 4.9 seconds.
2. Have the response stall in the broker, causing Gateway timeout at 5 seconds.
3. Have the reply reach the inbound adapter at 7 seconds.
4. Still feed the event into the Aggregator **if the workflow has not closed**.

At Gateway timeout time, **you cannot conclude the remote side effect failed**.

### 16.1. Gateway Late Reply Does Not Mean Late Business Event

~~~mermaid
sequenceDiagram
    participant C as Gateway Caller
    participant A as App / Gateway
    participant P as Provider
    participant W as Workflow Store
    C->>A: invoke quote()
    A->>P: request attempt A
    Note over A: replyTimeout elapsed
    A-->>C: Timeout / null per contract
    P-->>A: Reply attempt A arrives late
    A->>W: Check workflow state
    Note over W: Business deadline may still be open
~~~

A late reply for an **attempt** may have no waiting caller anymore, yet still represent valid business data. It can be saved into workflow state via a separate channel adapter, or discarded/audited if the contract already finalized the result.

Never try to resurrect an expired temporary `replyChannel` or push a late reply into a brand-new Java invocation. Use the business key and persisted state to decide whether to accept the late outcome.

### 16.2. Partial Results Must State the Kind of Partial

Two distinct situations:

- **Three terminal replies**, one supplier declined: the group is complete, `reportStatus=PARTIAL_SUPPLIER_FAILURE`.
- **Only two of three replies** before the business deadline: the group is incomplete, `reportStatus=INCOMPLETE` if the business emits a snapshot.

If you enable `sendPartialResultOnExpiry` on the Aggregator while keeping `QuoteReports.fromGroup()` which demands all three suppliers, the processor will throw on an incomplete group. To support partial releases, **write a dedicated processor** using the expected-provider manifest and missing-provider list.

### 16.3. Group Cleanup and Late Arrivals

After the Aggregator releases a group, Spring Integration can retain completed-group metadata to recognize late messages. If cleanup deletes the group completely, an old reply with the same `correlationId` can create a **new group**.

Choose retention periods based on broker redelivery, DLQ replay, and workflow schedules. If duplicate suppression must outlive metadata store retention, use a durable inbox/event ledger.

## 17. Retries and Idempotency: Keep the Business Key, Swap Attempt Tokens When Needed

When a gateway/outbound adapter times out, it may retry. Never mint a new business key per retry:

~~~text
logicalOperation = tenant-a / SHIP-901 / epoch 7 / provider PARTNER-A

attempt 1:
  businessCorrelationKey = shipment-quote:v1:tenant-a:SHIP-901:7
  operationId = quote:SHIP-901:7:PARTNER-A
  transportCorrelation = transport-001

attempt 2:
  businessCorrelationKey = shipment-quote:v1:tenant-a:SHIP-901:7
  operationId = quote:SHIP-901:7:PARTNER-A
  transportCorrelation = transport-002
~~~

**`businessCorrelationKey` and `operationId`** stay fixed per logical work. Transport correlation is managed by the gateway/protocol per attempt. A callback may need to map either `transport-001` or `transport-002` back to the same business operation.

### 17.1. Common Mistakes When Retrying the Entire Flow

Suppose quotes arrived from `PARTNER-A` and `PARTNER-B`, while `BACKUP` timed out:

~~~text
Attempt 1:
  PARTNER-A -> QUOTED
  PARTNER-B -> QUOTED
  BACKUP    -> timeout

Retry entire workflow:
  PARTNER-A called again
  PARTNER-B called again
  BACKUP called again
~~~

If providers merely compute a read-only quote, repeating calls carries lower side-effect risk. If providers **reserve capacity, charge fees, or book shipments**, repeating calls creates duplicate side effects. Scope retries as narrowly as needed and pass provider idempotency keys where supported.

### 17.2. Durable Inbox for Inbound Callbacks

An illustrative PostgreSQL schema:

~~~sql
CREATE TABLE quote_callback_inbox (
    tenant_id VARCHAR(48) NOT NULL,
    provider_id VARCHAR(48) NOT NULL,
    event_id VARCHAR(80) NOT NULL,
    group_key VARCHAR(240) NOT NULL,
    payload_digest VARCHAR(128) NOT NULL,
    status VARCHAR(24) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, provider_id, event_id)
);

CREATE INDEX quote_callback_inbox_group_idx
    ON quote_callback_inbox (group_key);

CREATE TABLE quote_provider_operation (
    tenant_id VARCHAR(48) NOT NULL,
    group_key VARCHAR(240) NOT NULL,
    provider_id VARCHAR(48) NOT NULL,
    operation_id VARCHAR(100) NOT NULL,
    status VARCHAR(24) NOT NULL,
    PRIMARY KEY (tenant_id, group_key, provider_id)
);
~~~

Primary keys match the contract: a provider's `eventId` is considered unique only within `tenant + provider`. If a producer sends the same `eventId` with a different payload digest, flag **`ID_CONFLICT`** and quarantine; never rewrite `eventId` to hide the error.

### 17.3. Crash Window Between Dedup and Dispatch

A flow lacking transactions/recovery can lose results:

~~~text
1. INSERT inbox event-1 status=SEEN
2. Commit
3. Crash before sending event-1 to Aggregator
4. Broker redelivers event-1
5. Code sees SEEN -> ignores
=> Aggregator never receives event-1
~~~

Solutions include a **transactional inbox/outbox**, or an inbox state machine distinguishing `RECEIVED`, `DISPATCH_PENDING`, `DISPATCHED`, and `PROCESSED` with a recovery worker. Never mark “seen” and drop every redelivery without knowing whether downstream actually received it.

### 17.4. One Terminal Outcome per Provider

If a timeout triggers an error handler to emit `UNAVAILABLE` and then the real provider replies `QUOTED` late, enforce an explicit policy:

- Never feed both outcomes into the Aggregator as if they were two different providers.
- Deduplicate by logical provider operation.
- If a report was already published, choose either freeze or an audited revision.
- If external state is `UNKNOWN`, reconcile before deciding.

**A Gateway timeout is not a business failure outcome that should silently overwrite a valid reply.**

## 18. Error Channel, DLQ, and Compensation

On a synchronous `DirectChannel`, exceptions usually propagate back to the caller. With `ExecutorChannel`, pollers, or brokers, errors can wrap into `ErrorMessage` per endpoint error-handling settings.

An `ErrorMessage` does not replace a `VerifiedQuoteResult`, and **`errorChannel` is not synonymous with a durable DLQ**. When a provider callback fails:

1. Identify `failedMessage` and trusted metadata (which may be absent in certain exceptions).
2. Classify schema/security/validation vs transient network/DB vs application bug.
3. Never admit security errors into groups.
4. Bound retries for transient errors, preserving `eventId`/`operationId`.
5. For terminal failures with complete trusted identity, emit a valid domain failure outcome if applicable.
6. If unsure whether side effects occurred, record `UNKNOWN` and reconcile.
7. Log full audit/trace context and move unprocessable messages to a durable quarantine/DLQ if contracted.

### 18.1. Protocol Errors Are Not Business Correlation Errors

| Symptom | Likely Cause | Check First |
| --- | --- | --- |
| Java Gateway timeout | No reply / Filter drop / transport delay | `replyChannel` and downstream reply path |
| JMS reply never reaches Gateway | Wrong `JMSCorrelationID`/`JMSReplyTo` | Protocol correlation and reply destination |
| AMQP RPC hangs | `replyTo`/correlation mismatch | `RabbitTemplate`/gateway configuration |
| TCP sends reply to wrong connection | Wrong/lost `ip_connectionId` | Connection routing metadata |
| Aggregator waits missing a member | Wrong business key or provider never replied | Verified business key + expected provider set |
| Two workflows mixed | Missing tenant/epoch, collision | Ingress trust boundary + key schema |
| Same provider counted twice | Broker redelivery/duplicate callback | Inbox/`eventId` + operation ledger |
| HTTP 202 yet no report appears | Callback never arrived or mapping failed | Workflow state + callback endpoint |

Never conclude “`correlationId` is wrong” merely because a Gateway timed out; pinpoint **which layer** mismatched: Java `replyChannel`, protocol request/reply, or business group.

### 18.2. When to Emit a Compensation Reply?

In a scatter-gather requiring a terminal outcome per branch, a recovery handler can emit a failure outcome after retries exhaust and the error is classified. However:

- Preserve the exact **business key and `providerId`**.
- Prevent emitting two outcomes if the provider replies late for real.
- Never mark a payment charge `UNAVAILABLE` when its state is `UNKNOWN`.
- Never copy untrusted `errorChannel`/`replyChannel` headers from a raw payload to send compensation.

If trusted metadata is insufficient, quarantine and alert for investigation; never guess a correlation key from an exception name.

## 19. Unit Test: Business Key Remains Stable Across Attempts

Before testing adapters, verify the business key contract with JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class QuoteCorrelationTest {

    @Test
    void sameVerifiedWorkflowHasSameKeyOnRetry() {
        QuoteCommand command =
                new QuoteCommand("SHIP-901", 7, 2);

        String attempt1 = QuoteCorrelation.key(
                "tenant-a", command);
        String attempt2 = QuoteCorrelation.key(
                "tenant-a", command);

        assertEquals(attempt1, attempt2);
        assertEquals(
                "shipment-quote:v1:tenant-a:SHIP-901:7",
                attempt1);
    }

    @Test
    void differentTenantOrEpochGetsDifferentKey() {
        QuoteCommand epoch7 =
                new QuoteCommand("SHIP-901", 7, 2);
        QuoteCommand epoch8 =
                new QuoteCommand("SHIP-901", 8, 2);

        assertNotEquals(
                QuoteCorrelation.key("tenant-a", epoch7),
                QuoteCorrelation.key("tenant-b", epoch7));
        assertNotEquals(
                QuoteCorrelation.key("tenant-a", epoch7),
                QuoteCorrelation.key("tenant-a", epoch8));
    }

    @Test
    void invalidTenantCannotEnterCorrelationGroup() {
        QuoteCommand command =
                new QuoteCommand("SHIP-901", 7, 1);
        assertThrows(IllegalArgumentException.class,
                () -> QuoteCorrelation.key(
                        "tenant-a:admin", command));
    }
}
~~~

This test verifies the deterministic key; it **does not** test `ShipmentAccessPolicy` or actual producer permissions. In production, two tenants can share shipment IDs, so cross-tenant tests are mandatory, not edge cases.

## 20. Integration Test: Messaging Gateway Replies to the Right Invocation

With `QuoteGatewayFlowConfig` from Section 7, an integration test should verify that:

1. The Gateway method returns a **`QuoteReceipt`**, not an internal Spring `Message`.
2. `businessCorrelationKey` passed by a trusted caller reaches the handler.
3. Two invocations with different keys receive their respective receipts.
4. Results do not depend on the caller manually creating or reading temporary `replyChannel`s.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(QuoteGatewayFlowConfig.class)
class QuoteGatewayFlowTest {

    @Autowired
    QuoteGateway gateway;

    @Test
    void gatewayReplyKeepsBusinessCorrelationKey() {
        QuoteCommand command =
                new QuoteCommand("SHIP-901", 7, 2);
        String key = QuoteCorrelation.key("tenant-a", command);

        QuoteReceipt reply = gateway.quote(command, key);

        assertNotNull(reply);
        assertEquals(key, reply.businessCorrelationKey());
        assertEquals("SHIP-901", reply.shipmentId());
        assertEquals("QUOTED", reply.status());
        assertEquals(new BigDecimal("150000"),
                reply.amountVnd());
    }

    @Test
    void twoInvocationsDoNotShareTheBusinessKey() {
        QuoteCommand first =
                new QuoteCommand("SHIP-901", 7, 1);
        QuoteCommand second =
                new QuoteCommand("SHIP-902", 4, 3);

        QuoteReceipt replyA = gateway.quote(
                first, QuoteCorrelation.key("tenant-a", first));
        QuoteReceipt replyB = gateway.quote(
                second, QuoteCorrelation.key("tenant-b", second));

        assertNotEquals(
                replyA.businessCorrelationKey(),
                replyB.businessCorrelationKey());
        assertEquals("SHIP-901", replyA.shipmentId());
        assertEquals("SHIP-902", replyB.shipmentId());
    }
}
~~~

**Conditions:** the example places the `@MessagingGateway` interface and `@IntegrationComponentScan` within the same scanned package scope. Spring Integration and `spring-test`/JUnit 5 must be on the classpath. Tests are not executed during content authoring; when integrating into a project, adjust packages and bean scanning to match your layout.

### 20.1. Testing Gateway Timeouts Differs from Testing Correlation

A separate test can configure a Gateway with a short `replyTimeout` and a downstream that emits no reply, verifying the timeout contract. Never send requests into a Gateway with an infinite timeout to test a “lost reply,” as it will hang the test suite.

In real HTTP/JMS/AMQP tests, verify the **reply adapter** honors transport-configured request/reply correlation. The two tests above test only a local Gateway and do not verify wire serialization.

## 21. Unit Test: Inbound Wire Mapper Rejects Spoofed Correlation

Create a stub registry allowing only `peer-partner-a` to report `PARTNER-A` results for active shipment `SHIP-901`.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class QuoteWireVerifierTest {

    private final QuoteWorkflowRegistry registry =
            new QuoteWorkflowRegistry() {
        @Override
        public boolean isActiveOrRecoverable(
                String tenantId, String shipmentId, int epoch) {
            return "tenant-a".equals(tenantId)
                    && "SHIP-901".equals(shipmentId)
                    && epoch == 7;
        }

        @Override
        public boolean mayReport(
                String peerId, String providerId) {
            return "peer-partner-a".equals(peerId)
                    && "PARTNER-A".equals(providerId);
        }
    };

    private final QuoteWireVerifier verifier =
            new QuoteWireVerifier(registry);

    private QuoteResultWire sample(String key) {
        return new QuoteResultWire(
                1, key, "evt-a-001", "PARTNER-A",
                "SHIP-901", 7, "QUOTED", "150000");
    }

    @Test
    void verifiedCallbackKeepsBusinessKey() {
        QuoteCommand identity =
                new QuoteCommand("SHIP-901", 7, 1);
        String expected =
                QuoteCorrelation.key("tenant-a", identity);

        VerifiedQuoteResult verified = verifier.verify(
                sample(expected),
                new VerifiedTransportPeer(
                        "peer-partner-a", "tenant-a"));

        assertEquals(expected,
                verified.businessCorrelationKey());
        assertEquals("tenant-a", verified.tenantId());
        assertEquals("PARTNER-A", verified.providerId());
        assertEquals(new BigDecimal("150000"),
                verified.totalVnd());
    }

    @Test
    void forgedBusinessKeyIsNotTrusted() {
        QuoteResultWire forged = sample(
                "shipment-quote:v1:tenant-admin:SHIP-901:7");

        assertThrows(SecurityException.class,
                () -> verifier.verify(
                        forged,
                        new VerifiedTransportPeer(
                                "peer-partner-a", "tenant-a")));
    }

    @Test
    void unauthorizedProviderIsRejected() {
        String valid = QuoteCorrelation.key(
                "tenant-a", new QuoteCommand("SHIP-901", 7, 1));

        assertThrows(SecurityException.class,
                () -> verifier.verify(
                        sample(valid),
                        new VerifiedTransportPeer(
                                "unknown-peer", "tenant-a")));
    }

    @Test
    void invalidAmountIsRejectedBeforeAggregation() {
        String key = QuoteCorrelation.key(
                "tenant-a", new QuoteCommand("SHIP-901", 7, 1));
        QuoteResultWire bad = new QuoteResultWire(
                1, key, "evt-a-002", "PARTNER-A",
                "SHIP-901", 7, "QUOTED", "-10");

        assertThrows(IllegalArgumentException.class,
                () -> verifier.verify(
                        bad,
                        new VerifiedTransportPeer(
                                "peer-partner-a", "tenant-a")));
    }
}
~~~

**Test conclusion:** wire events have no authority to arbitrarily choose internal correlation groups; the verified peer and workflow registry govern valid tenants and epochs. This test does not prove adapter mTLS/OAuth is configured; `VerifiedTransportPeer` must come from a real authentication layer.

### 21.1. Verifying Headers After Building the Message

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.integration.IntegrationMessageHeaderAccessor;

class QuoteMessageMapperTest {
    @Test
    void internalMessageHasTrustedCorrelationHeaders() {
        VerifiedQuoteResult result = new VerifiedQuoteResult(
                "shipment-quote:v1:tenant-a:SHIP-901:7",
                "evt-a-001", "PARTNER-A",
                "SHIP-901", 7, "tenant-a",
                "QUOTED", new java.math.BigDecimal("150000"));

        var message = QuoteMessageMapper.internal(result);
        assertEquals(result,
                message.getPayload());
        assertEquals(
                result.businessCorrelationKey(),
                message.getHeaders()
                        .get("businessCorrelationKey"));
        assertEquals(
                result.businessCorrelationKey(),
                message.getHeaders().get(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID));
        assertNull(message.getHeaders().get("errorChannel"));
    }
}
~~~

A fresh Spring Message **without a client `replyChannel`** is intentional in the async callback example; an inbound event does not return a Java Gateway reply over an expired temporary channel.

## 22. Integration Test: Three Adapters Deliver Replies to the Same Business Group

In a pure Spring context test, we simulate that HTTP, JMS, and AMQP inputs have already been verified and sent into `verifiedQuoteCallbacks`. The goal is to prove **content-based group correlation** is independent of arrival order or originating adapter.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(QuoteCallbackFlowConfig.class)
class QuoteCallbackFlowTest {

    @Autowired
    @Qualifier("verifiedQuoteCallbacks")
    MessageChannel input;

    @Autowired
    @Qualifier("quoteAggregationOutput")
    QueueChannel reports;

    @BeforeEach
    void clearReports() {
        while (reports.receive(0) != null) {
            // Drain output queue if test context is reused.
        }
    }

    private VerifiedQuoteResult result(
            String tenantId,
            String shipmentId,
            int epoch,
            String eventId,
            String providerId,
            String status,
            String totalVnd) {

        QuoteCommand identity =
                new QuoteCommand(shipmentId, epoch, 1);
        String key = QuoteCorrelation.key(tenantId, identity);

        return new VerifiedQuoteResult(
                key,
                eventId,
                providerId,
                shipmentId,
                epoch,
                tenantId,
                status,
                totalVnd == null ? null : new BigDecimal(totalVnd));
    }

    private void send(VerifiedQuoteResult verified) {
        assertTrue(input.send(
                QuoteMessageMapper.internal(verified)));
    }

    @Test
    void repliesFromThreeAdaptersJoinSameGroup() {
        // Arrival order: AMQP, HTTP, JMS.
        send(result("tenant-a", "SHIP-901", 7,
                "evt-backup-901", "BACKUP", "QUOTED", "190000"));
        send(result("tenant-a", "SHIP-901", 7,
                "evt-a-901", "PARTNER-A", "QUOTED", "150000"));

        assertNull(reports.receive(0));

        send(result("tenant-a", "SHIP-901", 7,
                "evt-b-901", "PARTNER-B", "QUOTED", "160000"));

        Message<?> reply = reports.receive(0);
        assertNotNull(reply);
        QuoteAggregationReport report =
                (QuoteAggregationReport) reply.getPayload();

        assertEquals(3, report.receivedCount());
        assertEquals("COMPLETE", report.status());
        assertEquals(
                "shipment-quote:v1:tenant-a:SHIP-901:7",
                report.businessCorrelationKey());
        assertEquals("PARTNER-A",
                report.bestQuote().providerId());
        assertEquals(new BigDecimal("150000"),
                report.bestQuote().totalVnd());
        assertNull(reports.receive(0));
    }

    @Test
    void tenantAndWorkflowEpochStayIsolated() {
        send(result("tenant-a", "SHIP-902", 1,
                "a1", "PARTNER-A", "QUOTED", "100000"));
        send(result("tenant-a", "SHIP-902", 1,
                "a2", "PARTNER-B", "QUOTED", "120000"));

        // Two messages from different scopes do not fill the missing member.
        send(result("tenant-b", "SHIP-902", 1,
                "b1", "BACKUP", "QUOTED", "90000"));
        send(result("tenant-a", "SHIP-902", 2,
                "a3", "BACKUP", "QUOTED", "85000"));
        assertNull(reports.receive(0));

        send(result("tenant-a", "SHIP-902", 1,
                "a4", "BACKUP", "QUOTED", "110000"));

        QuoteAggregationReport report =
                (QuoteAggregationReport)
                        reports.receive(0).getPayload();

        assertEquals(
                "shipment-quote:v1:tenant-a:SHIP-902:1",
                report.businessCorrelationKey());
        assertEquals(3, report.outcomes().size());
        assertNull(reports.receive(0));
    }

    @Test
    void unavailableIsATerminalOutcomeNotAMissingReply() {
        send(result("tenant-a", "SHIP-903", 1,
                "a903", "PARTNER-A", "QUOTED", "150000"));
        send(result("tenant-a", "SHIP-903", 1,
                "b903", "PARTNER-B", "UNAVAILABLE", null));
        send(result("tenant-a", "SHIP-903", 1,
                "c903", "BACKUP", "QUOTED", "180000"));

        QuoteAggregationReport report =
                (QuoteAggregationReport)
                        reports.receive(0).getPayload();

        assertEquals(3, report.receivedCount());
        assertEquals("PARTIAL_SUPPLIER_FAILURE", report.status());
        assertEquals("PARTNER-A",
                report.bestQuote().providerId());
    }
}
~~~

### 22.1. Limitations of This Integration Test Suite

These tests **do not actually start an HTTP server, Kafka/JMS/AMQP broker, or TCP connection**. They verify the convergence point **after an adapter has verified data and built an internal Spring Message**.

Therefore you cannot conclude yet that:

- Real HTTP/JMS/AMQP header mappings preserve `businessCorrelationKey`.
- `JMSCorrelationID`/`JMSReplyTo` or AMQP `replyTo` echo accurately.
- TCP serializers preserve correlation fields.
- Broker redeliveries cause no duplicates.
- A multi-instance `MessageGroupStore` handles concurrent updates safely.

Those require **contract/integration tests at the transport boundary**.

### 22.2. Testing Transport Contracts with a Broker or Mock HTTP Server

Design a dedicated adapter test suite:

| Adapter | Test Action | Assertion |
| --- | --- | --- |
| HTTP outbound gateway | Stub server echoes request metadata | Proper payload/header mapping + returned reply |
| HTTP inbound callback | Send callback with forged key | Blocked before `verifiedQuoteCallbacks` |
| JMS outbound gateway | Remote responder returns matching `JMSCorrelationID` | Gateway receives the exact request's reply |
| JMS outbound gateway | Responder returns wrong `JMSCorrelationID` | Never delivers reply to another caller |
| AMQP gateway | Two RPC requests run concurrently | Replies match the right invocations |
| AMQP adapters | Consumer redelivers old `eventId` | Dedup ledger protects outcome/effects |
| TCP gateway | Reply on same connection per protocol | Right connection/request |
| TCP collaborating adapters | Two requests on different connections | Application key still correlates properly |

You can use **WireMock/MockWebServer** for HTTP or Testcontainers/broker test fixtures for JMS/AMQP, depending on the project. Set bounded timeouts so tests cannot hang indefinitely if a reply never arrives.

### 22.3. Testing When a Callback Truly Arrives Late

With the same `businessCorrelationKey`:

1. Send `PARTNER-A` and `PARTNER-B`; verify no full report exists yet.
2. Let the synchronous Gateway attempt end with a simulated timeout.
3. Send a valid `BACKUP` callback within the business deadline.
4. Verify workflow state accepts the late outcome per policy.
5. Once the business deadline has passed, verify late callbacks are audited/quarantined or create a revision rather than silently mutating old reports.

Do not inspect only `QueueChannel` outputs: inspect the **workflow store** when simulating lost replies across adapters.

## 23. If You Only Have Adapter Callbacks, Do You Need a Gateway?

**Not necessarily.** A system receiving HTTP/JMS callbacks from three providers can use inbound adapters, verified mappers, and an Aggregator directly without a Java Messaging Gateway waiting on each reply.

~~~text
Inbound Adapter 1 ----+
Inbound Adapter 2 ----+--> Verify -> Correlate -> Aggregate -> Persist result
Inbound Adapter 3 ----+
~~~

A Gateway is helpful when a Java module wants to invoke a flow as a method call, or when the protocol genuinely uses request/reply. However, if a process runs for minutes and must survive restarts, a Gateway call with a temporary `replyChannel` **is not a workflow state store**.

### 23.1. Hybrid Pattern

You can combine both:

1. An HTTP inbound gateway receives the start command.
2. An application service persists durable workflow state and dispatches tasks via outbound adapters.
3. The HTTP gateway immediately returns **`AcceptedResponse`** with a `trackingId`.
4. Inbound adapters receive asynchronous callbacks and correlate using the business key.
5. Once all outcomes arrive, the Aggregator updates state and emits a completion event.
6. The client polls a status API or receives an authorized notification.

**This uses request/reply to accept work, not request/reply to block until the entire workflow finishes.** Separating the two contracts avoids tying up HTTP threads for minutes.

### 23.2. When the Correlation Key Is Absent from the Callback

A provider returns only `providerTicketId` instead of `businessCorrelationKey`:

~~~json
{
  "providerTicketId": "ticket-553",
  "status": "QUOTED",
  "priceVnd": "150000"
}
~~~

In this case, persist a durable mapping **`providerTicketId → trustedTenantId + businessCorrelationKey + providerId + operationId`** when sending the request. When the callback arrives, look up the mapping and authenticate the callback source; never spawn a new workflow from an arbitrary `ticketId`.

If the mapping is lost across a restart, you need recovery/reconciliation. Never fill in a random `correlationId` just to push the message into the Aggregator.

## 24. Observability: Tracking All Three Correlation Layers

A system without correlation metrics often reports only “Gateway timeout,” unable to tell whether the fault lies in an adapter header mapper, a provider, or an Aggregator group. Logs should distinguish:

1. **Business workflow identity**: group key / tracking ID.
2. **Transport attempt**: `JMSCorrelationID`, AMQP request correlation, HTTP request ID, or TCP connection ID.
3. **Logical event identity**: `eventId`, `providerId`, `operationId`.

### 24.1. Sample Outbound Log

~~~json
{
  "stage": "quote-outbound",
  "businessCorrelationRef": "opaque-quote-901",
  "providerId": "PARTNER-A",
  "operationId": "quote:SHIP-901:7:PARTNER-A",
  "transport": "JMS",
  "transportAttempt": 2,
  "status": "SENT"
}
~~~

### 24.2. Sample Inbound Adapter Log

~~~json
{
  "stage": "quote-inbound-verified",
  "businessCorrelationRef": "opaque-quote-901",
  "providerId": "PARTNER-A",
  "eventId": "evt-provider-778",
  "transport": "HTTP_CALLBACK",
  "verified": true,
  "dedupStatus": "FIRST_ARRIVAL",
  "workflowState": "IN_PROGRESS"
}
~~~

**These are sample logs**, not automatic Spring Integration outputs. Never log credentials, `Authorization` headers, sensitive raw payloads, or live `replyChannel` objects. Use opaque/redacted references in logs if business keys contain sensitive tenant/shipment IDs.

### 24.3. Recommended Metrics

| Metric | Measures What? |
| --- | --- |
| **`gateway_invocations_total{method,status}`** | Java Gateway calls and outcomes |
| **`gateway_reply_timeout_total{method}`** | Calls that timed out waiting for replies |
| **`transport_requests_total{protocol,provider}`** | Outbound attempts |
| **`transport_reply_mismatch_total{protocol}`** | Responses failing to match transport requests |
| **`adapter_header_mapping_failure_total{protocol}`** | Missing/malformed header mappings |
| **`business_correlation_verification_failed_total{reason}`** | Inbound wire keys mismatching verified bindings |
| **`callback_duplicate_total{provider}`** | Deduplicated callback events |
| **`callback_identity_conflict_total{provider}`** | Same event ID with differing payload/group |
| **`callback_recovery_total{outcome}`** | Retries/reconciliations/quarantines |
| **`aggregation_group_pending`** | Incomplete business groups |
| **`aggregation_group_age_seconds`** | Age of waiting groups |
| **`aggregation_complete_total{status}`** | `COMPLETE`/`NO_OFFER`/`PARTIAL` outcomes |
| **`aggregation_incomplete_total`** | Business deadlines passed with missing providers |
| **`aggregation_late_event_total{reason}`** | Replies arriving after group closure |

Never use arbitrary `businessCorrelationKey`, `tenantId`, `shipmentId`, `eventId`, or transport correlation tokens as metric labels when cardinality is high. Put them in traces/logs with proper retention and access control.

### 24.4. A Reply Timeout Metric Alone Is Insufficient

Two systems can have the same Gateway timeout rate for entirely different reasons:

- **A:** an adapter fails to serialize the business key, leaving the business Aggregator short of members.
- **B:** transport reply correlation matches fine, yet the remote service is genuinely slow.

To tell them apart, check verified callback accepted, pending groups, transport mismatches, supplier latency, and message store metrics. Never fix an identity bug merely by bumping timeouts.

## 25. Runbook: Responses Reach the Broker Yet Never Join the Right Workflow

### Step 1 — Identify the Contract to Complete

Are you waiting for **one reply from a Java Gateway** or **three terminal events in a business Aggregator**? The two contracts are distinct and can finish at different times.

### Step 2 — Derive the Business Group from Trusted Input

Verify tenant, `shipmentId`, `workflowEpoch`, and key algorithm version. If outbound and inbound business keys differ, inspect canonicalization, the workflow registry, and header/body mappings.

### Step 3 — Inspect Transport Correlation

| Transport | Check |
| --- | --- |
| HTTP | Same request's response or a separate callback? Are `HeaderMapper`/body schemas right? |
| JMS | `JMSReplyTo`, `JMSMessageID`/`JMSCorrelationID`, or custom correlation property |
| AMQP | `replyTo`, `correlationId`, and RPC gateway settings |
| TCP | `ip_connectionId`, serializer/deserializer, and gateway/adapter pairing |
| File | Manifest/batch identity; filename/ID unchanged across retries |

If protocol correlation failed, the application aggregator may never have received the message. If protocol delivery succeeded yet the business group is wrong, fix the mapper/registry instead of blindly tweaking `JMSCorrelationID`.

### Step 4 — Authenticate and Validate the Inbound Envelope

Verify the peer is authorized to emit events for `providerId` and tenant. Compare the wire `businessCorrelationKey` against the value computed from the authoritative registry. On mismatch, quarantine/alert and keep it out of the Aggregator.

### Step 5 — Check Inbox and Redeliveries

Look up `eventId`/`providerId` in the inbox:

- Never seen: trace delivery/routing/network failure.
- `RECEIVED` but not `DISPATCHED`: run recovery/outbox.
- `DISPATCHED` yet missing from Aggregator: inspect acks/store/transactions.
- `COMPLETED`: reply is likely a duplicate; do not repeat side effects.
- Differing payload digest for same identity: `ID_CONFLICT`.

### Step 6 — Inspect the Aggregator Group

For the right key, how many **unique providers** arrived—not just how many `Message` objects? Is the expected set satisfied? Is `ReleaseStrategy` mistakenly waiting on `sequenceSize` unsuitable for independent callbacks? Has the group already expired or completed?

### Step 7 — Check Late/Timeout Policies

The Gateway may time out before a callback arrives while the business workflow stays active. Check the deadline and late-event policy before replaying. Never send a late reply to a closed temporary `replyChannel`.

### Step 8 — Execute Controlled Remediation

- Retry the exact **logical operation**, keeping business key and event identity intact.
- Reconcile when remote side-effect state is `UNKNOWN`.
- Quarantine schema/authorization mismatches.
- Emit a report revision if business rules allow post-deadline updates.
- Never invent a new correlation key merely to avoid an existing group.

### Step 9 — Verify After Remediation

Each active request/reply reaches its valid caller; each business group holds only authorized terminal outcomes; no duplicate side effects occurred; and pending group counts return to normal.

## 26. Common Design Mistakes

| Mistake | Consequence | Correction |
| --- | --- | --- |
| Using `MessageHeaders.ID` as business correlation | Each hop/rebuild changes the ID | Derive/look up a stable group key |
| Copying client `X-Correlation-ID` into Aggregator | False joins or cross-tenant leaks | Verify tenant+binding, create internal key |
| Minting a new UUID at each inbound adapter | Callbacks of one workflow split across groups | One durable mapping or deterministic key |
| Equating `JMSCorrelationID` with `orderId` | Concurrent attempt replies mis-match | Let JMS Gateway manage protocol tokens |
| Routing callbacks back to temporary Gateway channels | Channel lifetime already expired | Workflow store + async result |
| Serializing all `MessageHeaders` over TCP | Live objects are non-portable | Wire DTO / selected header mapper |
| Using `ip_connectionId` as group key | Merges unrelated requests on one connection | Business payload/operation key |
| Dropping business ID across HTTP → AMQP | Callbacks cannot correlate | Explicit body/header mapping |
| Trusting unverified callback `providerId` | Supplier spoofs another member | Peer identity + allowlist |
| Using `group.size()==3` | Duplicates hide missing suppliers | Unique-provider release + inbox dedup |
| Filtering out `UNAVAILABLE` suppliers | Group waits forever | Emit terminal failure outcome if appropriate |
| Treating `ErrorMessage` as a supplier result | `Throwable` is not a domain outcome | Typed recovery/compensation |
| Gateway timeout = workflow `FAILED` | Drops valid later callbacks | Separate transport timeout from business deadline |
| Retrying the whole workflow when one provider fails | Repeats side effects on other sources | Per-provider retry + idempotency |
| Persisting dedup only before dispatch | Crash loses events | Transaction/outbox/recovery |
| Immediately deleting completed groups | Late replies spawn phantom new groups | Retention and persistent ledger |
| Sharing `batchId` across all subgroups | Mixes item outputs | Key includes `itemId` + epoch |
| Unbounded active groups | Overloads `MessageGroupStore` | Quotas, timeouts, cleanup, monitoring |

## 27. Practice Exercise: Combining HTTP Gateway, JMS Adapter, and TCP Callbacks

Design a shipment dispatch-authorization workflow:

~~~text
HTTP inbound gateway /api/shipments/{id}/dispatch-check
     -> verified ingress / business group
     -> publish 3 checks:
          WAREHOUSE  via JMS
          COMPLIANCE via HTTP
          TRANSPORT  via TCP
     -> each source emits an independent event
     -> inbound adapters
     -> verify + correlation
     -> Aggregator
     -> DispatchDecision
~~~

### 27.1. Exercise Contract

Identifiers:

~~~java
record DispatchCheckRequest(
        String shipmentId,
        int workflowEpoch,
        String requestedBy) {}

record DispatchPartResult(
        String eventId,
        String businessCorrelationKey,
        String sourceId,
        String status,
        String errorCode) {}

record DispatchDecision(
        String businessCorrelationKey,
        String decision,
        java.util.List<DispatchPartResult> evidence) {}
~~~

Rules:

- Each source must return one **terminal outcome**: `ALLOWED`, `DENIED`, or `UNAVAILABLE` per contract.
- The workflow decides `READY` only when `WAREHOUSE`, `COMPLIANCE`, and `TRANSPORT` are all `ALLOWED`.
- If a source returns `DENIED`, it may emit `REJECTED` once all required terminal outcomes arrive.
- If a source has not sent an event, never assume `DENIED`; remain `IN_PROGRESS` or move to `INCOMPLETE` at deadline.
- Tenant comes from verified principal; shipment and epoch must be checked against the workflow registry.
- `eventId` stays constant across redeliveries; transport request tokens may differ per attempt.

### 27.2. Implementation Steps

1. Write an ingress service verifying tenant/shipments and generating a versioned `businessCorrelationKey`.
2. Build a Messaging Gateway for short-lived Java calls returning an accepted receipt.
3. Build three outbound adapters/gateways matching one-way or request/reply contracts.
4. Design a shared wire envelope containing `schemaVersion`, `eventId`, `sourceId`, business key, and status.
5. Configure per-transport `HeaderMapper`/converters without sending live `replyChannel`/`errorChannel` objects over the wire.
6. Build inbound mappers authenticating producers and looking up bindings in the registry.
7. Write a dedup inbox protecting `eventId` and detecting `ID_CONFLICT`.
8. Build an Aggregator with `CorrelationStrategy` on the business key and `ReleaseStrategy` checking all three source IDs.
9. Add group timeouts, business deadlines, and `INCOMPLETE` reporting policies.
10. Scope JMS Gateway reply correlation and TCP `ip_connectionId` to their proper layers.
11. Submit two requests from different tenants with the same `shipmentId`; verify zero mixing.
12. Have the HTTP source return a late callback after the Gateway attempt times out; verify state/revision policy.
13. Redeliver a JMS event and verify no duplicate terminal outcomes or side effects occur.
14. Simulate a crash between inbox insert and dispatch, proving recovery/outbox works.
15. Add metrics, trace logs, and a runbook for missing replies.

### 27.3. Test Matrix

| Case | Condition | Expected |
| --- | --- | --- |
| A | All three sources `ALLOWED` | One `DispatchDecision` `READY` |
| B | `COMPLIANCE` `DENIED`, two sources `ALLOWED` | Policy-compliant decision, no missing member |
| C | `TRANSPORT` does not reply | `IN_PROGRESS` → `INCOMPLETE` at deadline |
| D | Duplicate `WAREHOUSE` event | Not counted as a fourth source |
| E | Tenants A and B share `shipmentId` | Two independent groups |
| F | Same shipment, epochs 3 and 4 | Two independent workflows |
| G | Client-spoofed `X-Correlation-ID` | Ignored/blocked at ingress |
| H | Wrong `JMSCorrelationID` | Reply never delivered to another caller |
| I | Wrong TCP `ip_connectionId` | Never misrouted to wrong connection |
| J | HTTP callback after reply timeout | Business state handles per policy |
| K | Unsupported payload `schemaVersion` | Rejected/quarantined, never generates random key |
| L | Restart before Aggregator release | Durable store/recovery preserves progress |
| M | Redelivery after group metadata deleted | Persistent ledger prevents duplicate effects |

### 27.4. Self-Check Questions

1. Why is a Gateway `replyChannel` not synonymous with a business correlation key?
2. When does a Spring Integration Gateway use a temporary anonymous reply channel?
3. Must correlation sent across an adapter always be Spring's `CORRELATION_ID` header?
4. When should you use a wire envelope instead of copying all `MessageHeaders`?
5. Does HTTP `202 Accepted` mean the business workflow finished?
6. Which components does `JMSCorrelationID` connect?
7. How does AMQP `replyTo` differ from a business callback destination?
8. Can TCP `ip_connectionId` represent multiple business requests?
9. Why must a client-supplied correlation ID be verified?
10. Does a retried workflow need a new business key?
11. If a callback lacks a business key yet carries `providerTicketId`, how do you handle it?
12. Why are three callbacks from the same provider insufficient for a three-provider group?
13. How does a mapper error differ from a Gateway timeout?
14. Does an `ErrorMessage` on `errorChannel` automatically become an Aggregator member?
15. Why is an idempotency ledger still required even when `correlationId` is stable?
16. When should a sync Gateway be replaced with an async workflow?
17. If a Splitter emits three items, what components must the correlation key for provider replies include?
18. When a callback arrives past the business deadline, may it silently alter an already-published report?

## 28. Pre-Deployment Checklist for Correlation Across Gateways and Adapters

- Architecture docs clearly separate **business key**, **Gateway reply channel**, **protocol correlation**, and **event ID**.
- Ingress authenticates tenant, producer, business object, and workflow epoch before stamping keys.
- All adapters share the same key schema/version and canonicalization rules.
- Same logical workflow and redeliveries produce the same `businessCorrelationKey`; different tenants/epochs produce different keys.
- Messaging Gateways enforce bounded reply timeouts and explicit contracts when no reply arrives.
- Live Java `replyChannel`/`errorChannel` objects are never serialized into wire payloads.
- HTTP `HeaderMapper` is verified for required custom headers, not just standard headers.
- HTTP `202 Accepted` is kept distinct from final business completion.
- JMS request/reply follows `JMSCorrelationID`/`JMSReplyTo` and actual `correlation-key` configuration.
- AMQP request/reply uses protocol `replyTo`/correlation per contract.
- TCP connection routing keeps `ip_connectionId` where replies are sent, never as a business key.
- TCP serializers/deserializers and framing specify exact headers/fields crossing the wire.
- Callbacks without correlation keys have durable mappings from provider ticket/operation IDs.
- Wire envelopes carry `schemaVersion`, `eventId`, `providerId`, workflow identity, and typed status.
- Arbitrary headers/correlation keys from unauthenticated zones are never trusted.
- Inbound mappers recompute/look up keys, verify tenant and event origin, and catch mismatches.
- Parent workflow Aggregator group keys stay separate from child Splitter/Scatter-Gather technical correlation.
- `ReleaseStrategy` checks exact member ID sets rather than merely counting `Message` objects.
- Duplicate events are caught by an inbox/ledger before counting group completion.
- Transactions/outbox/recovery guard against crashes between dedup and dispatch.
- Side effects rely on provider idempotency keys or reconciliation independent of group metadata.
- Gateway, transport, Aggregator, and business deadline timeouts are defined separately.
- Late-reply policies are documented: discard/audit, freeze, revision, or reconcile.
- `MessageGroupStore`/`LockRegistry` support restarts and multi-instance concurrency when durable state is needed.
- Error channels/DLQs/quarantine have consumers, retries, and retention matching the contract.
- Raw business keys, transport tokens, or high-cardinality IDs are omitted from metric labels.
- Tests cover at least local Gateway, wire verifier, Aggregator grouping, cross-tenant, cross-epoch, callback duplicates, protocol mismatches, timeouts, and restarts.
- Queue, socket, broker, and connection-pool exhaustion are evaluated under concurrent load.
- Runbooks clearly separate **protocol reply matching** failures from **business group correlation** failures.

## 29. Summary of the Three-Layer Model

A reliable Content-based correlation architecture across Gateways and Adapters can be read from the outside in:

~~~mermaid
flowchart TB
    A["Trusted ingress<br/>tenant + shipment + epoch"] --> B["Business correlation key<br/>stable across retries"]
    B --> C["Gateway / outbound adapter"]
    C --> D["Protocol correlation<br/>JMS / AMQP / TCP / HTTP"]
    D --> E["Remote provider"]
    E --> F["Inbound adapter / callback"]
    F --> G["Verify producer + envelope + eventId"]
    G --> H["Rebuild internal Message<br/>business key"]
    H --> I["Dedup / Aggregator / workflow state"]
    I --> J["Business result / idempotent effect"]
~~~

**Layer 1 — Business:** the correlation key tells whether messages belong to the same tenant, shipment, and workflow epoch. It must stay stable across transports and redeliveries.

**Layer 2 — Communication:** Gateways and adapters use `replyChannel`, `JMSCorrelationID`/`JMSReplyTo`, AMQP `replyTo`/correlation, or TCP `ip_connectionId` to route a **transport reply** back to the right endpoint. These values usually live shorter than the business workflow and can change across attempts.

**Layer 3 — Trust and Recovery:** a callback joins a group only after verifying source, content, event ID, and workflow binding. Inbox/outbox, `MessageGroupStore`, timeouts, duplicate suppression, and idempotency ensure flows **neither lose nor duplicate business effects** across broker/network failures.

**Conclusion:** Correlation across Gateways and Adapters is not about copying a header named `correlationId` everywhere. Maintain **trusted business identity across boundaries**, while letting **Gateways/protocols manage their own request/reply correlation**. When asynchronous callbacks exist, business workflows must never depend on expired temporary `replyChannel`s. Separating all three layers, testing per-transport mappings, and placing retries/idempotency at the right boundaries lets Spring Integration reliably coordinate Router, Transformer, Splitter, Aggregator, Gateway, and error channels.

## References

- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): temporary `replyChannel`, gateway configuration, reply timeouts, and request/reply rules.
- [Spring Integration Reference — HTTP Header Mappings](https://docs.spring.io/spring-integration/reference/http/header-mapping.html): HTTP headers, `HeaderMapper`, custom mappings, and inbound/outbound directions.
- [Spring Integration Reference — HTTP Support](https://docs.spring.io/spring-integration/reference/http.html): HTTP inbound/outbound gateways and channel adapters.
- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): JMS inbound/outbound gateways, `JMSCorrelationID`, `JMSReplyTo`, and `correlation-key`.
- [Spring AMQP — Spring Integration Reference](https://docs.spring.io/spring-amqp/reference/integration-reference.html): inbound/outbound adapters and request/reply gateways with AMQP.
- [Spring Integration Reference — TCP Message Correlation](https://docs.spring.io/spring-integration/reference/ip/correlation.html): gateways, collaborating adapters, `ip_connectionId`, and transferring selected headers over TCP.
- [Spring Integration Reference — TCP Gateways](https://docs.spring.io/spring-integration/reference/ip/tcp-gateways.html): connection-based request/reply and inbound/outbound gateway notes.
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): `CorrelationStrategy`, `ReleaseStrategy`, `MessageGroupStore`, group timeouts, and late arrivals.
- [Spring Integration Reference — Splitter](https://docs.spring.io/spring-integration/reference/splitter.html): sequencing headers and nested groups.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `ErrorMessage`, `errorChannel`, and synchronous vs asynchronous error differences.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): `DirectChannel`, `ExecutorChannel`, `QueueChannel`, and dispatch semantics.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): deduplication tooling and limits of idempotency advice.
- [Enterprise Integration Patterns — Correlation Identifier](https://www.enterpriseintegrationpatterns.com/patterns/messaging/CorrelationIdentifier.html): pattern for linking replies to requests and distinguishing corresponding messages.
- [Enterprise Integration Patterns — Messaging Gateway](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingGateway.html): hiding messaging details from the calling application.

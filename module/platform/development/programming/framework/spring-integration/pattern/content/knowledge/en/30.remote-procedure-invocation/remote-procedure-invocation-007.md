# Request and Reply Contracts

## 1. Context: A Java Call Crossing a Message Boundary

In the **SPRING_INTEGRATION_PATTERN** module, we learn to implement **Enterprise Integration Patterns** with **Spring Integration** to build loosely coupled, scalable, and observable message flows. When combining Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, a request can pass through many endpoints before yielding an answer. **Remote Procedure Invocation (RPI/RPC)** in particular highlights this issue: calling code looks like an ordinary Java method, yet the executing side may be another service, another thread, or another broker/network.

Suppose an ordering service wants to fetch a shipping quote:

~~~java
ShippingQuoteReply reply = quoteGateway.quote(
        request,
        verifiedTenantId,
        trustedBusinessRequestId);
~~~

The caller may expect a simple call, yet the system must answer many questions:

- Which fields, types, and version must the request have?
- Does a successful reply prove the price was calculated, or only that the request was accepted?
- Is an unsupported product a **business rejection** or an infrastructure failure?
- When no reply is received, could the request **already have been processed**?
- Which key joins two out-of-order replies with two waiting requests?
- If a broker redelivers a request, does processing cause a **duplicate side effect**?
- Is a new version of the request compatible with an un-upgraded consumer?
- How do tenant, authorization, and trace context cross the transport boundary?

A sound contract must define **both request and reply**, including schema, validation, identity, business outcome, error semantics, deadline, correlation, and compatibility. Writing a Java method signature or one sample JSON payload is not enough.

~~~mermaid
sequenceDiagram
    participant C as Java caller
    participant G as Spring Messaging Gateway
    participant R as Request channel
    participant S as Remote service / adapter
    participant P as Reply channel
    C->>G: quote(request, tenant, requestId)
    G->>R: Message(payload=request, headers=context)
    R->>S: Request over flow or transport
    S-->>P: Reply with correlation
    P-->>G: Matching response
    G-->>C: typed result or failure
~~~

### Lesson Objectives

After this lesson, you will be able to:

1. Distinguish the **RPC integration style** from **request-reply messaging** and local Java calls.
2. Build a **typed request/reply contract** with explicit version, identity, validation, currency, and time.
3. Distinguish **success**, **business rejection**, **accepted/pending**, **technical failure**, and **timeout/unknown**.
4. Map request/reply using **Spring Integration Messaging Gateway** and **Service Activator** without losing business correlation.
5. Properly understand timeouts, reply channels, network correlation, and idempotency across retries.
6. Design compatibility and schema evolution across multiple producer/consumer versions.
7. Test contracts using JUnit, Spring Integration tests, and contract tests over HTTP/JMS/AMQP.
8. Write a runbook to diagnose lost requests, late replies, schema-invalid responses, or duplicated effects.

## 2. Remote Procedure Invocation Is an Integration Style, Not a Guaranteed Local Call

In Enterprise Integration Patterns, **Remote Procedure Invocation** is one of the integration styles: one program invokes an operation provided by another program through an interface that looks close to a method. Spring Integration offers **Messaging Gateways** and request-reply adapters that can create an RPC-like experience, yet the implementation still relies on **messages, channels, endpoints, and transport**.

| Aspect | Local Java Call | RPC over Network/Messaging |
| --- | --- | --- |
| Execution location | Same process | May be another process/host |
| Latency | Usually short and low variance | Depends on queues, network, remote load |
| Data | Object references | Bytes/serialized DTOs or messages |
| Errors | Usually direct exceptions | Timeouts, connection loss, partial failure, remote error |
| Lifecycle | Thread/call stack | Request state, reply correlation, deadlines, retries |
| Exactly-once effect | Controllable within a local transaction | Not automatically guaranteed across services/brokers |
| Version | Classes in the same deployment | Producer and consumer may run different versions |

**Common mistake:** treating an RPC timeout like a Java exception thrown before the method ran. In reality, the remote side may have written to the database while the reply was lost; the caller does not know the outcome. Therefore, a request/reply contract needs **status lookup, idempotency, or reconciliation** for side-effecting operations.

### 2.1. When Is RPI a Good Choice?

- The caller needs a fast result to continue processing, such as fetching a quote or checking info.
- The operation has short, bounded expected execution time.
- There is a clear fallback/handling path when the remote is unavailable.
- Request/reply schemas are stable enough with clear ownership and versioning.
- Timeouts/retries and fallbacks are designed around business meaning.

### 2.2. When Should You Choose Asynchronous Messaging?

- The operation takes minutes or depends on humans/external partners.
- Multiple receivers must respond independently.
- The caller does not need the final outcome immediately on the initial request.
- Inter-service failures must be tolerated via durable workflow state.
- High traffic requires buffering/backpressure and recovery after restarts.

In those cases, use **command + accepted receipt + completion event**, or **Scatter-Gather/Aggregator** with a defined timeout and release strategy. A synchronous Gateway is not a durable workflow engine.

## 3. A Contract Has More Layers Than a JSON Payload

A request/reply contract typically has at least five layers:

~~~mermaid
flowchart TB
    C["Business operation semantics"] --> D["Payload schema / validation"]
    D --> I["Identity + correlation"]
    I --> T["Transport + timeout"]
    T --> F["Failure + retry + versioning"]
~~~

| Layer | Request Must Specify | Reply Must Specify |
| --- | --- | --- |
| **Operation** | What to do; side-effecting or read-only | Completed, rejected, or only accepted |
| **Schema** | Required fields, types, units, version | Result type, money, error code, nullable fields |
| **Identity** | requestId, operationId, tenant, business key | Echo requestId, correlation/causation |
| **Transport** | Channel/endpoint, deadline, auth | Reply path, protocol correlation, TTL |
| **Failure policy** | Retryability, idempotency, dedup scope | Business rejection vs. technical/unknown |

An API declaring only:

~~~java
String call(Map<String, Object> request);
~~~

is hard to use correctly: callers do not know field names, data may be missing, it is unclear whether `String` is a price or an error, and timeout handling is undefined.

A typed API:

~~~java
ShippingQuoteReply quote(
        ShippingQuoteRequest request,
        String verifiedTenantId,
        String businessRequestId);
~~~

is clearer, yet still needs **documentation + schema validation + error policy + integration tests**. A method signature alone does not solve compatibility when remote deployments change.

### 3.1. Request and Reply Contracts Must Be Reviewed Together

If the request supports `currencyCode="USD"` while the reply only has `long amountVnd`, the consumer cannot interpret it accurately. If the request carries `businessRequestId` for dedup while the reply fails to echo identity, an async caller can attach a reply to the wrong invocation.

**Rule:** never add a request field affecting business outcomes without reviewing the reply's invariants and fields.

### 3.2. Categorizing Fields by Owner

| Field | Authoritative Source | Can You Trust Raw Self-Declared Client Input? |
| --- | --- | --- |
| `sku`, `quantity` | Parsed/validated payload | Can be input, but must be validated |
| `tenantId` | Authentication/authorization context | **No** |
| `businessRequestId` | Verified registry/client operation ID | Not completely |
| `businessCorrelationKey` | Workflow registry/trusted adapter | **No** |
| `traceRef` | Observability context | Usable after validation, not as authority |
| `replyChannel` | Spring runtime | Never accept directly from untrusted request |
| `JMSCorrelationID` | Transport request-reply protocol | Not automatically equal to business key |

## 4. Running Example: Shipping Rate Quote Request

We design an RPC-like **Shipping Rate Quote** flow to illustrate **request and reply contracts**. To keep focus on messaging, the example uses a fixed internal rate table, calls no real carrier service, and **performs no charge/reservation**.

### 4.1. Illustrative Wire Request

~~~json
{
  "contractVersion": 1,
  "requestId": "req-quote-00091",
  "operation": "QUOTE_SHIPPING",
  "payload": {
    "shipmentId": "SHIP-901",
    "serviceLevel": "EXPRESS",
    "parcelCount": 2,
    "currencyCode": "VND"
  }
}
~~~

Tenant and authorization info are verified at ingress. If passed across a remote wire envelope, `tenantRef` or signature/identity claims may be included per contract, but **never treat a `tenantId` JSON field alone as proof of authorization**.

### 4.2. Illustrative Successful Wire Reply

~~~json
{
  "contractVersion": 1,
  "requestId": "req-quote-00091",
  "outcome": "QUOTED",
  "result": {
    "shipmentId": "SHIP-901",
    "amount": "160000",
    "currencyCode": "VND",
    "rateVersion": "rate-demo-v1",
    "validUntil": "2026-11-21T03:10:00Z"
  }
}
~~~

Money is a **decimal string** on the wire to avoid floating-point precision loss across JSON consumers. `validUntil` is a UTC **Instant** with explicit timezone. Timestamps in the example only illustrate the schema; production must calculate validity from real policies/rate versions.

### 4.3. Illustrative Business-Rejected Wire Reply

~~~json
{
  "contractVersion": 1,
  "requestId": "req-quote-00091",
  "outcome": "REJECTED",
  "error": {
    "code": "SERVICE_LEVEL_UNAVAILABLE",
    "retryable": false,
    "message": "Service level not offered for this shipment"
  }
}
~~~

This is a **valid business rejection of the operation**, not an HTTP/JMS connection exception. The caller can display the reason or prompt for another service level. A DB/network error must not be disguised as `REJECTED` just to make the flow emit a reply.

### 4.4. Case with No Reply

~~~text
Request sent at T0
Caller waits until T0 + 5s
No reply received
Caller observes: TIMEOUT / UNKNOWN
~~~

**Never infer `REJECTED` or `NOT_EXECUTED`.** The remote service may not have received it yet, may still be processing, may have finished with a late reply, or may have committed before the connection dropped. For side-effecting operations, perform lookup/reconciliation by `requestId`/`operationId`.

## 5. Schema and Invariants to Test

| Property | Rule in Example |
| --- | --- |
| `contractVersion` | Request/Reply version **1** |
| `requestId` | Stable for the same logical request; never regenerated on retries |
| `operation` | `QUOTE_SHIPPING`; other versions must be explicitly defined |
| `shipmentId` | Valid non-blank string |
| `serviceLevel` | Enum `STANDARD` or `EXPRESS` |
| `parcelCount` | Integer from 1 to 1000 |
| `currencyCode` | Only `VND` supported in this example |
| Reply `requestId` | Equals the corresponding request's `requestId` |
| Reply `outcome` | `QUOTED` or `REJECTED` |
| Reply QUOTED | Has price/currency/rateVersion/validUntil; no error |
| Reply REJECTED | Has stable error code; no successful quote |
| Clock | ISO-8601 absolute timestamp with timezone, independent of client clock |
| Authorization | Tenant/shipment ownership verified before processing |

### 5.1. Monetary Units and Types

Never use `float`/`double` to transmit monetary amounts and round on the other end:

~~~java
// Unsuitable for a money contract:
double amount = 0.1 + 0.2;
~~~

In Java, use **BigDecimal** with explicit currency/scale policy. On the JSON wire, a decimal `String` avoids parsing discrepancies across JavaScript, Python, and Java.

### 5.2. Nulls and Optional Fields

Avoid a "one-DTO-for-everything" reply with `price=null`, `error=null`, `status=null` forcing clients to guess valid combinations. Use a **discriminated union**: `outcome=QUOTED` has `result`; `outcome=REJECTED` has `error`. If an operation is only accepted for async processing, add `ACCEPTED` with its own schema rather than overloading `QUOTED`.

### 5.3. Never Version Using Java Class Names

A wire payload should not rely on `com.example.dto.QuoteCommand` serialized via arbitrary Java object serialization. Use published schemas/operation IDs/versions, and let the parser select DTOs via an allowlist/registry.

## 6. Java 17: Typed Request with Construction-Time Validation

The example uses Java 17 records to create a strongly typed request. The contract version lives in the DTO, not just in a comment.

~~~java
import java.util.Objects;

enum ShippingServiceLevel {
    STANDARD,
    EXPRESS
}

record ShippingQuoteRequest(
        int contractVersion,
        String requestId,
        String shipmentId,
        ShippingServiceLevel serviceLevel,
        int parcelCount,
        String currencyCode) {

    ShippingQuoteRequest {
        if (contractVersion != 1) {
            throw new IllegalArgumentException(
                    "UNSUPPORTED_REQUEST_VERSION");
        }
        if (requestId == null
                || !requestId.matches("[A-Za-z0-9_:-]{1,96}")) {
            throw new IllegalArgumentException("INVALID_REQUEST_ID");
        }
        if (shipmentId == null
                || !shipmentId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("INVALID_SHIPMENT_ID");
        }
        Objects.requireNonNull(serviceLevel, "serviceLevel");
        if (parcelCount < 1 || parcelCount > 1000) {
            throw new IllegalArgumentException("INVALID_PARCEL_COUNT");
        }
        if (!"VND".equals(currencyCode)) {
            throw new IllegalArgumentException("UNSUPPORTED_CURRENCY");
        }
    }
}
~~~

The constructor protects **request syntax and invariants**. It does not prove the shipment belongs to the authenticated tenant. Security must be enforced at ingress/facade or a service authorized to query the registry.

### 6.1. Which Field Is the Request Identity?

In this example, `requestId` represents the **logical request identity**. Resending the same request after a timeout must keep the same `requestId`. However, a new quote with a different `serviceLevel` choice is a new logical request and needs a new `requestId`.

If an application allows reusing the same `requestId` with a different payload, downstream must treat it as an **identity conflict** or a contract-governed revision—never silently overwrite the previous result.

### 6.2. Validate in the Proper Order

1. Raw bytes/JSON/XML are parsed according to supported versions.
2. Check sizes, field types, nulls, enums, timestamps.
3. Construct `ShippingQuoteRequest` and run schema validation.
4. Authenticate producer/principal and authorize shipment/tenant access.
5. Attach trusted metadata and send into the `IntegrationFlow`.
6. Check domain-specific invariants before generating a reply.

Do not pass DTOs from `ObjectMapper` into unprotected handlers if the schema allows **client-specified polymorphic class names**. Use explicit discriminators/allowlists.

## 7. Java 17: Typed Reply Distinguishing Outcomes

A reply should **force consumers to distinguish success from rejection**, instead of guessing nullable fields:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.Currency;
import java.util.Objects;

record QuoteMoney(BigDecimal amount, Currency currency) {
    QuoteMoney {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
        if (!Currency.getInstance("VND").equals(currency)) {
            throw new IllegalArgumentException("UNSUPPORTED_CURRENCY");
        }
        amount = amount.setScale(0, RoundingMode.UNNECESSARY);
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("NEGATIVE_AMOUNT");
        }
    }
}

sealed interface ShippingQuoteReply
        permits ShippingQuoteSuccess, ShippingQuoteRejected {
    int contractVersion();
    String requestId();
}

record ShippingQuoteSuccess(
        int contractVersion,
        String requestId,
        String shipmentId,
        QuoteMoney price,
        String rateVersion,
        Instant validUntil) implements ShippingQuoteReply {

    ShippingQuoteSuccess {
        if (contractVersion != 1) {
            throw new IllegalArgumentException(
                    "UNSUPPORTED_REPLY_VERSION");
        }
        Objects.requireNonNull(requestId, "requestId");
        Objects.requireNonNull(shipmentId, "shipmentId");
        Objects.requireNonNull(price, "price");
        if (rateVersion == null || rateVersion.isBlank()) {
            throw new IllegalArgumentException("MISSING_RATE_VERSION");
        }
        Objects.requireNonNull(validUntil, "validUntil");
    }
}

record ShippingQuoteRejected(
        int contractVersion,
        String requestId,
        String code,
        boolean retryable,
        String safeMessage) implements ShippingQuoteReply {

    ShippingQuoteRejected {
        if (contractVersion != 1) {
            throw new IllegalArgumentException(
                    "UNSUPPORTED_REPLY_VERSION");
        }
        Objects.requireNonNull(requestId, "requestId");
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("MISSING_ERROR_CODE");
        }
        Objects.requireNonNull(safeMessage, "safeMessage");
    }
}
~~~

**Note on Java records:** compact constructors can reassign input parameters like `amount = amount.setScale(...)`; the record field receives the normalized value. `RoundingMode.UNNECESSARY` intentionally rejects fractional values incompatible with VND. Never silently round shipping fees.

### 7.1. Business Rejection Is Not a Throwable

`ShippingQuoteRejected` is for a **known business outcome** (e.g., EXPRESS service level does not support certain shipments). An authorization failure, malformed JSON, database timeout, or JVM exception should not automatically become a `ShippingQuoteRejected` with code `UNKNOWN`.

### 7.2. Error Codes Must Be Stable

When the error code is `SERVICE_LEVEL_UNAVAILABLE`, consumers can build appropriate user messages. The `safeMessage` field is only for display or sanitized debugging; **never branch logic on English sentence text**, as wording may change during localization or deployments.

### 7.3. Replies Should Echo requestId

`requestId` is present in both variants. Consumers can verify `reply.requestId` matches the awaiting request; on mismatch, do not return it to another caller. Over transport request/reply, **protocol correlation** and late-reply handling are also required.

## 8. QuoteDecisionService: Deterministic and Bounded Results

We build an illustrative service with no I/O and no side effects. Price is computed from parcel count using fixed sample data, using `Clock` so `validUntil` is cleanly testable.

~~~java
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Currency;
import java.util.Objects;

final class QuoteDecisionService {
    private final Clock clock;

    QuoteDecisionService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    ShippingQuoteReply decide(ShippingQuoteRequest request) {
        // Illustrative business rule:
        // EXPRESS supports at most 20 parcels in this demo.
        if (request.serviceLevel() == ShippingServiceLevel.EXPRESS
                && request.parcelCount() > 20) {
            return new ShippingQuoteRejected(
                    1, request.requestId(),
                    "SERVICE_LEVEL_UNAVAILABLE",
                    false,
                    "Express service unavailable for this package count");
        }

        long unitPriceVnd = request.serviceLevel()
                == ShippingServiceLevel.EXPRESS ? 80_000L : 30_000L;
        BigDecimal total = BigDecimal.valueOf(unitPriceVnd)
                .multiply(BigDecimal.valueOf(request.parcelCount()));

        return new ShippingQuoteSuccess(
                1,
                request.requestId(),
                request.shipmentId(),
                new QuoteMoney(total, Currency.getInstance("VND")),
                "rate-demo-v1",
                Instant.now(clock).plus(Duration.ofMinutes(10)));
    }
}
~~~

Two calls with the same request can yield the same **amount/rateVersion** yet **different `validUntil`** when using a real-time Clock. If business rules require replaying the same `requestId` to return the **exact same reply**, production must **persist the quote snapshot/rateVersion/expiry** or cache the outcome by idempotency key rather than relying solely on deterministic pricing math.

### 8.1. Never Use Clock.now to Generate Request Identity

Processing time changes across retries. Never use `Instant.now()` as `requestId`, `correlationKey`, or `operationId`. Identities must be assigned by a registry/ingress and stay stable for the same logical operation.

### 8.2. When Is the Service Allowed to Return REJECTED?

For instance, `EXPRESS` with 21 parcels violates the **business offering policy** while the request schema is valid, so the service has enough facts to return a conclusive rejection. Conversely, a network timeout while querying a catalog provides no evidence the customer was rejected; the operation may still be pending/unknown.

## 9. Gateway Interface: Java Request to Spring Message

Spring Integration provides **Messaging Gateway** to hide `MessageChannel` and `MessageHeaders` from callers:

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@MessagingGateway(defaultRequestChannel = "rpcQuoteRequests")
interface ShippingQuoteGateway {

    @Gateway(requestTimeout = 2_000, replyTimeout = 5_000)
    ShippingQuoteReply quote(
            @Payload ShippingQuoteRequest request,
            @Header("trustedTenantId") String tenantId,
            @Header("businessRequestId") String businessRequestId);
}
~~~

**Method mapping:**

~~~text
Java Gateway call
  request argument -> Spring Message.payload
  tenantId argument -> header trustedTenantId
  businessRequestId -> header businessRequestId

Framework:
  adds MessageHeaders.ID / timestamp
  manages reply channel if a reply is expected

Downstream:
  Service Activator handles payload and selected headers
  returns ShippingQuoteReply
~~~

The Gateway method expects **ShippingQuoteReply**, though at Spring runtime it may be backed by message dispatch, a Service Activator, an HTTP/JMS/AMQP outbound gateway, or a multi-hop Router path.

### 9.1. Do Not Let Clients Decide trustedTenantId

An HTTP request with `X-Tenant-Id: tenant-admin` must not be passed straight into `trustedTenantId`. The Gateway proxy only maps values; **it does not verify authorization**. An application service must verify the principal and shipment permissions before invoking the interface.

### 9.2. Tying businessRequestId to requestId

In this example, `@Header("businessRequestId")` mirrors `request.requestId()` so downstream can check that both sources match. This helps catch mapping bugs or spoofed headers, though it does not replace ingress verification.

If you rely solely on `requestId` in the payload and do not need a mirror header, omit the extra argument/header. Never maintain multiple identity copies without a consistency rule.

### 9.3. Do Not Dump Timeout Policies Arbitrarily into Payloads

`requestTimeout` and `replyTimeout` are runtime settings of the Gateway invocation, not domain deadlines. If the contract needs a **business deadline** meaningful across transports/restarts, represent it explicitly as a versioned field/metadata with a UTC instant and dedicated expiry rules.

## 10. Service Activator: Receiving the Right Contract and Producing a Reply

The handler accepts `@Payload` and `@Header` to verify identity. It **does not construct a new reply `MessageChannel` itself**.

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

final class QuoteRpcHandler {
    private final QuoteDecisionService service;

    QuoteRpcHandler(QuoteDecisionService service) {
        this.service = service;
    }

    @ServiceActivator(inputChannel = "rpcQuoteRequests")
    public ShippingQuoteReply handle(
            @Payload ShippingQuoteRequest request,
            @Header("trustedTenantId") String tenantId,
            @Header("businessRequestId") String businessRequestId) {

        if (tenantId == null || tenantId.isBlank()) {
            throw new SecurityException("MISSING_VERIFIED_TENANT");
        }
        if (!request.requestId().equals(businessRequestId)) {
            throw new SecurityException("REQUEST_ID_HEADER_MISMATCH");
        }
        return service.decide(request);
    }
}
~~~

**Two safeguards:** required `@Header` lets the framework catch missing headers during parameter binding; the method body compares `requestId` to block mismatches. Still, a syntactically valid `tenantId` string does not prove the tenant owns the shipment; authorization remains with the layer holding the verified principal/registry.

### 10.1. Do Not Build a Reply Message That Drops the Temporary replyChannel

When the Service Activator returns `ShippingQuoteReply` as the payload, Spring Integration builds the reply `Message` and manages the reply path per framework semantics. If the handler manually constructs a new `Message` without the required `replyChannel`, the waiting Gateway may never receive the result.

### 10.2. One-Way and Two-Way Need Separate Contracts

If you replace the method with `void handle(...)` and only write to a database, the Gateway method `quote()` still expects a typed reply. The flow may end with no reply or time out. For one-way commands, use a `void` Gateway method or return a defined meaningful **ack/accepted result** rather than faking `QUOTED`.

## 11. Spring Integration Configuration for an RPC-Like Flow

The example uses **DirectChannel** to focus on contracts and request/reply. No HTTP server, broker, or real remote service is needed.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
@IntegrationComponentScan
class QuoteRpcConfig {

    @Bean
    MessageChannel rpcQuoteRequests() {
        return new DirectChannel();
    }

    @Bean
    Clock quoteClock() {
        // Fixed Clock only for reproducible example/test results.
        // Production uses Clock.systemUTC().
        return Clock.fixed(
                Instant.parse("2026-11-21T03:00:00Z"),
                ZoneOffset.UTC);
    }

    @Bean
    QuoteDecisionService quoteDecisionService(Clock quoteClock) {
        return new QuoteDecisionService(quoteClock);
    }

    @Bean
    QuoteRpcHandler quoteRpcHandler(QuoteDecisionService service) {
        return new QuoteRpcHandler(service);
    }
}
~~~

Place the `ShippingQuoteGateway` interface in the same package (or a package scanned by `@IntegrationComponentScan`). Spring Integration creates the Gateway proxy for the registered interface, and the `QuoteRpcHandler` endpoint is created from `@ServiceActivator`.

**Do not register another `IntegrationFlow` bean consuming `rpcQuoteRequests` in this context if only one handler is desired.** A `DirectChannel` dispatches to a chosen subscriber; two competing handlers make results unpredictable.

### 11.1. Diagram of the Sample Configuration

~~~mermaid
flowchart LR
    C["Application service"] --> G["ShippingQuoteGateway"]
    G -->|"QuoteRequest + trusted headers"| D["rpcQuoteRequests DirectChannel"]
    D --> A["QuoteRpcHandler @ServiceActivator"]
    A --> S["QuoteDecisionService"]
    S -->|"ShippingQuoteReply"| A
    A -->|"Gateway-managed reply path"| G
    G -->|"Typed result"| C
~~~

In this topology, request dispatch and handler execution run mostly **synchronously** on the caller thread. `replyTimeout=5_000` is not a hard execution deadline for Java code running directly inside `DirectChannel`; if the handler hangs, the `receive` timeout does not necessarily interrupt the running handler.

### 11.2. Calling the Gateway

~~~java
ShippingQuoteRequest request = new ShippingQuoteRequest(
        1,
        "req-quote-00091",
        "SHIP-901",
        ShippingServiceLevel.EXPRESS,
        2,
        "VND");

ShippingQuoteReply reply = gateway.quote(
        request,
        "tenant-a",               // only after authorization
        request.requestId());
~~~

In practice, this call should live inside a facade that has verified the actor/tenant/shipment. `gateway` is an injected Spring bean; never do `new ShippingQuoteGateway()` as it is an interface/proxy.

### 11.3. Decoupling Business Logic from Messaging

`QuoteDecisionService.decide(request)` is a plain Java method with no imports of `MessageChannel`, `ErrorMessage`, or `Gateway`. `QuoteRpcHandler` acts as the adapter from Spring `Message` to domain service; `ShippingQuoteGateway` acts as the reverse adapter from Java API to messaging.

~~~text
Caller -> Gateway -> Message -> Service Activator
                               -> Domain service
Caller <- Gateway <- Reply Message <- result
~~~

This keeps Java code easy to test, while Routers, Transformers, or remote adapters can change without forcing domain services to accept Spring `Message` directly.

## 12. Correlation Contract: At Least Three Types of Identity

An RPC-like invocation typically involves **multiple identities with distinct scopes**:

| Identity | Scope | Source | On Retry? |
| --- | --- | --- | --- |
| **requestId / businessRequestId** | Logical business request | Ingress/operation registry | Preserved if same request |
| **businessCorrelationKey** | A workflow or group | Verified tenant + entity + epoch | Preserved within workflow |
| **Spring MessageHeaders.ID** | Single Message instance | Framework | Can change |
| **temporary replyChannel** | Single Gateway invocation | Spring Gateway runtime | Usually differs per invocation |
| **JMSCorrelationID / AMQP correlationId** | Transport request/reply exchange | Adapter/broker protocol | Can change per attempt |
| **traceId/spanId** | Execution tracing | Tracing infrastructure | Trace/span per retry topology |

Do not lump all these fields together as "correlationId" in business code when they solve different problems.

### 12.1. businessRequestId Verifies the Reply

In synchronous flows, the Gateway usually maintains a temporary reply channel. Still, the reply echoes `requestId` because:

- When serialized over a network, the remote response must self-describe which request it answers.
- When persisted/replayed, a Java channel object cannot be relied upon.
- When the remote returns the wrong `requestId`, the consumer can detect a mismatched response.
- In logs/audits, `requestId` traces one logical invocation across multiple hops.

### 12.2. One Workflow Can Have Multiple requestIds

Suppose workflow `SHIP-901` includes:

~~~text
workflow key = shipping:tenant-a:SHIP-901:epoch-7

quote request:
  requestId = req-quote-00091

reserve stock request:
  requestId = req-stock-00501

book carrier request:
  requestId = req-carrier-00888
~~~

The three operations have **distinct `requestIds`** while sharing the parent workflow's `businessCorrelationKey`. Using the workflow key as the idempotency key for all three operations would cause a ledger to block distinct operations as duplicates.

### 12.3. Correlation Is Not Authorization

An attacker knowing a `requestId` or business group key is not authorized to receive the reply. Transport adapters must authenticate producers/callers, verify tenant ownership, and restrict destinations; never use `requestId` as a bearer token.

### 12.4. Splitter/Aggregator Have Their Own Correlation Scope

If a request is split by a Splitter into multiple parcel requests, `CORRELATION_ID`, `SEQUENCE_NUMBER`, and `SEQUENCE_SIZE` describe a child group. That does not necessarily equal the shipment's `businessCorrelationKey`. The Aggregator needs correlation/release strategies tailored to the **exact scope**, not merely `group.size()` when messages may be redelivered.

## 13. Reply Path in Spring Messaging Gateway

For a method with a return type, the Gateway typically uses a **temporary reply destination**:

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as Messaging Gateway
    participant H as RPC handler
    C->>G: quote(request)
    G->>H: Message + temporary replyChannel
    H-->>G: ShippingQuoteSuccess
    G-->>C: typed ShippingQuoteReply
~~~

In the example, the Service Activator returns a `ShippingQuoteSuccess` or `ShippingQuoteRejected` as payload so the framework routes it back along the reply path set up by the Gateway.

### 13.1. Reply Path Diverted to a QueueChannel

Counter-example:

~~~text
Gateway replyChannel = temporary-A

Handler:
  sends ShippingQuoteSuccess to standalone "quoteOutputQueue"

No bridge / reply wiring back to temporary-A

Gateway:
  waits on temporary-A
  eventually has no reply
~~~

A fixed `outputChannel` does not automatically become the `replyChannel` the caller is waiting on. If the flow uses a separate reply queue, you need a **bridge/correlator** or properly configured gateway adapter so replies return to the right invocation.

### 13.2. Reply Arriving Twice

A request/reply Gateway method expects one corresponding result. If downstream Scatter-Gather produces three replies, the Gateway cannot guess which reply is the "final result." Use an Aggregator to emit **one business result** per release strategy, with timeouts and deduplication.

### 13.3. Late Replies

If a caller times out after 5 seconds, a reply arriving at second 8 may no longer have a waiting receiver on the temporary reply channel. If the business result still matters, store it in workflow state keyed by `requestId`/business key rather than feeding it to a different waiting invocation.

### 13.4. Returning Null or No Reply

A one-way `void` handler, a discarding Filter, or a flow with no responder can leave the Gateway without a timely reply. **Never default `null` to mean business rejection.** The client contract must distinguish no reply (technical outcome) from a `ShippingQuoteRejected` reply carrying business meaning.

## 14. Outcome States: Business and Technical Are Two Orthogonal Axes

A resilient system avoids collapsing every exception into a semantically poor `FAILED` enum.

| Caller Observes | What Can Be Concluded | What Caller Should Do |
| --- | --- | --- |
| **ShippingQuoteSuccess** | Quote computed per contract and rate version | Use within validity period |
| **ShippingQuoteRejected** | Explicit business rule rejection | Modify request / show reason |
| **Accepted/Pending** (if in contract) | Request accepted, no final outcome yet | Poll / subscribe to workflow |
| **Validation exception** | Invalid request schema/headers | Fix input; usually do not retry as-is |
| **Authorization exception** | Caller lacks permission | Stop, audit |
| **Network/send failure** | Uncertain whether remote received | Lookup/retry per idempotency policy |
| **Reply timeout** | No timely reply received | UNKNOWN; do not assume failed |
| **Remote technical error** | Processing system encountered a failure | Bounded retry/recovery if retryable |

### 14.1. Error Reply or Exception?

A contract may return a structured **technical error envelope** (e.g., `UPSTREAM_UNAVAILABLE`) when the remote knows the failure and can safely reply. However, **no reply received** cannot be represented by a server-sent remote envelope because the server may not have sent anything. The client must have its own timeout/exception branch.

### 14.2. Business Rejection Is Not Always retryable=false

The example uses `SERVICE_LEVEL_UNAVAILABLE, retryable=false`. Some business refusals may be `TEMPORARILY_UNAVAILABLE`, but the contract must specify **under what conditions** retrying is allowed. Never rely on a single `retryable` boolean for side-effecting operations; deadlines, backoff, idempotency, and committed state also matter.

### 14.3. Do Not Leak Stack Traces in Replies

`safeMessage` should only contain consumer-safe text—never SQL, tokens, internal addresses, hostnames, or stack traces. Diagnostic details belong in access-controlled logs/traces and audits.

## 15. Request Deadline, Gateway Timeout, and Transport TTL

There are at least five kinds of time limits:

| Type | Where Applied? | What It Guarantees |
| --- | --- | --- |
| **Gateway requestTimeout** | Sending Message to request channel | Bounds waiting when send can block |
| **Gateway replyTimeout** | Waiting for reply after dispatch | Caller does not wait forever |
| **Business deadline** | Schema/workflow state | Cutoff beyond which the operation is no longer useful |
| **Transport TTL / expiration** | Broker/network | Expired messages may be dropped/undelivered |
| **Provider operation timeout** | Remote client/library | Bounds a single HTTP/gRPC/JMS attempt |

These limits are not interchangeable. Setting `replyTimeout=5000` does not guarantee the remote stops processing after 5 seconds or rolls back committed side effects.

### 15.1. Deadlines Must Be Absolute Timestamps Across Multiple Hops

~~~json
{
  "requestId": "req-quote-00091",
  "businessDeadline": "2026-11-21T03:02:00Z"
}
~~~

If deadline is a v2 contract field, specify UTC timezone, clock source, skew tolerance, and late-arrival behavior. Each hop can compute **remaining budget** from the deadline instead of adding 5 seconds per service and extending end-to-end latency indefinitely.

### 15.2. Timeout and Cancellation Are Not Synonymous

The caller can time out while the remote keeps running. If cancellation must be supported, define a **dedicated cancel operation contract** with `operationId`, authorization, and outcomes `CANCELLATION_ACCEPTED`/`CANNOT_CANCEL`/`ALREADY_COMMITTED`; never assume Java thread interruption across a network rolls back a remote DB.

### 15.3. Do Not Retry Past the Deadline Out of Habit

Retry policies must account for total time: attempts, backoff, jitter, provider timeouts, and deadline. Once the deadline expires, transition to timeout/unknown and query/reconcile if side effects exist rather than doing futile work.

## 16. Contracts over HTTP, JMS, AMQP, and Remote Adapters

The `DirectChannel` example above runs in a single JVM to illustrate request/reply. Moving the service out-of-process requires passing the contract through **serialization + protocol-specific request/reply correlation + security**.

~~~mermaid
flowchart LR
    G["Java Messaging Gateway"] --> F["IntegrationFlow"]
    F --> A["HTTP / JMS / AMQP outbound gateway"]
    A --> W["Wire contract v1"]
    W --> B["Remote inbound adapter"]
    B --> S["Remote handler"]
    S --> R["Wire reply v1"]
    R --> A
    A --> F
    F --> G
~~~

| Transport | Request/Reply Mechanism | Contract Concerns |
| --- | --- | --- |
| **HTTP** | Request + HTTP response over connection/request lifecycle | Status codes, content type, JSON schema, timeouts, retry safety |
| **JMS** | JMSReplyTo/JMSCorrelationID and request/reply destinations | Message converter, correlation strategy, reply listener, DLQ |
| **AMQP** | replyTo, correlation properties, broker routing | Message converter, publisher confirms vs. business replies, reply queues |
| **TCP** | Framing, connection/request correlator per adapter | Message boundaries, connection lifetime, serializer |
| **gRPC/other RPC** | Protocol-defined status, metadata, and message schema | Deadlines, status mappings, auth, compatibility |

Do not apply identical request/reply rules to all adapters. HTTP `202 Accepted` means something different from `200` containing a final quote. A broker ACK may only confirm **transport receipt**, not that the business operation committed.

### 16.1. HTTP: Separating Status Codes and Business Outcomes

A contract might publish:

| HTTP Response | Meaning | Body |
| --- | --- | --- |
| 200 | Quote calculated successfully | `ShippingQuoteSuccess` |
| 422 | Valid schema, violates offering policy | `ShippingQuoteRejected` |
| 202 | Command accepted, processed async | `AcceptedReceipt` with operationId/statusUrl |
| 400 | Invalid JSON/shape | Standardized validation error |
| 401/403 | Authentication/authorization failed | Safe error, no internal leaks |
| 429/503 | Rate limit/upstream unavailable | Technical error with retry guidance if appropriate |
| Timeout/no response | Caller does not know outcome | UNKNOWN, query status if needed |

These are **design suggestions**, not automatic Spring Integration mappings for these exact status codes. HTTP inbound/outbound gateways must be configured with converters, status mappings, and exception handling per contract.

### 16.2. JMSCorrelationID Does Not Necessarily Equal Business requestId

A JMS outbound gateway may manage a correlation token for **one request attempt**. `businessRequestId` is the identity across retries and persisted workflows. Do not force transport tokens and business request IDs to always be identical unless **adapter configuration, collision rules, and version contracts** are verified.

### 16.3. AMQP Broker ACK Differs from Business Reply

Publisher confirms / broker ACKs only prove the broker received or processed up to a stage. A `ShippingQuoteSuccess` reply must come from the quote-calculating handler per v1 schema. If a consumer crashes before replying, broker redelivery/retry logic must handle it properly rather than treating a broker confirm as a business value.

### 16.4. Header Mapper and Envelope

A Spring `Message` may contain:

~~~text
payload: ShippingQuoteRequest
headers:
  trustedTenantId: tenant-a
  businessRequestId: req-quote-00091
  replyChannel: temporary Java object
~~~

After serializing to HTTP/JMS, **not every header is preserved**. Business identity needs a wire schema or explicit selected broker properties, and remote ingress must **re-verify** tenant authorization. Never serialize a live `replyChannel` object into JSON expecting another JVM to use it.

### 16.5. Testing Round-Trip Through a Real Adapter

1. Construct a request with explicit version and `requestId`.
2. Gateway creates the Spring `Message`.
3. Converter/adapter serializes it to bytes + allowed protocol headers.
4. Remote parser/validator constructs the typed request.
5. Remote handler returns a reply with a matching `requestId`.
6. Reply via transport adapter maps back to a Spring `Message`.
7. Gateway caller receives the exact reply or a classified error.

Unit tests with `ObjectMapper` do not replace a **JMS `HeaderMapper`/HTTP integration test** when the goal is verifying network metadata.

## 17. Versioning and Compatibility of Request/Reply

Requests and replies can evolve at different cadences. Any change must consider **producers, consumers, persisted messages, DLQs, and replays**.

### 17.1. Three Types of Changes

| Change | Example | Assessment |
| --- | --- | --- |
| **Additive/optional** | Reply adds nullable `estimatedDeliveryDate` | Potentially backward compatible if consumers ignore unknown fields |
| **Semantics change** | `amount` changes from gross to net | **Semantically breaking** even if name and type stay unchanged |
| **Structural breaking** | `requestId` changes to integer, `currencyCode` changes enum | Requires version/migration |

**Structural compatibility does not equal business compatibility.** A v1 consumer reading v2's `amount` field while misinterpreting gross vs. net is more dangerous than an explicit parse error.

### 17.2. Rules for Tolerant Yet Unambiguous Consumers

Consumers may ignore **unknown optional fields** if schema policy allows. However, never:

- Guess currency when `currencyCode` is missing.
- Default an unknown enum to `QUOTED` or `REJECTED`.
- Convert float `amount` to decimal without knowing precision.
- Use a different `businessRequestId` for the same logical retry.
- Shift `validUntil`'s timezone to system default.

### 17.3. Never Blindly Copy Reply Version from Request

A server receiving a v1 request may return a v1 reply per negotiated contract. If the server returns a v2 reply, the caller must know how to decode and check compatibility. Never stamp `contractVersion=1` onto a payload with v2 semantics just to keep old parsers quiet.

### 17.4. Versioned Upcaster

~~~text
Wire Request v1 ----> Parser V1 ---+
                                   +-> CanonicalRequest -> Domain service
Wire Request v2 ----> Parser V2 ---+

Domain result -> Reply projection v1 / v2
              -> Wire serializer by negotiated contract
~~~

An upcaster may only fill defaults for new fields **when valid business meaning exists**. For example, if v1 lacked `insuranceFlag`, defaulting v2 to `false` can be wrong if v1 implied insurance under another policy.

### 17.5. Version in URL, Header, or Body?

You can use `/v1/quote`, versioned media types, a schema registry, `contractVersion` in the envelope, or versioned broker topics. Pick **one consistent strategy**, document how parsers identify versions, and avoid conflicting version markers without validation.

### 17.6. Error Codes Are Also Part of the Contract

If a consumer handles `SERVICE_LEVEL_UNAVAILABLE`, renaming it to `UNSUPPORTED_LEVEL` can break backward compatibility. Version your error code taxonomy, maintain a mapping/deprecation plan, and write contract tests for error replies.

## 18. Trusted Facade: Who Is Allowed to Call the Remote Operation?

Never let an HTTP controller pass `X-Tenant-Id` straight into the Gateway. A facade verifies identity and shipment authorization first, then creates/attaches `requestId` per contract.

### 18.1. Application Contracts

~~~java
record AuthenticatedQuoteActor(
        String principalId,
        String tenantId) {
}

interface QuoteAuthorization {
    void requireAllowed(
            AuthenticatedQuoteActor actor,
            ShippingQuoteRequest request);
}

interface QuoteRequestRegistry {
    void verifyLogicalIdentity(
            AuthenticatedQuoteActor actor,
            ShippingQuoteRequest request);
}
~~~

`AuthenticatedQuoteActor` must come from verified authentication/session/mTLS/JWT/broker identity, **not** a raw tenant claim. `QuoteRequestRegistry` can verify `requestId` is a valid identity for this request—whether duplicate payload or a new revision.

### 18.2. Facade Separating Authorization from the Gateway

~~~java
final class QuoteApplicationFacade {
    private final ShippingQuoteGateway gateway;
    private final QuoteAuthorization authorization;
    private final QuoteRequestRegistry registry;

    QuoteApplicationFacade(
            ShippingQuoteGateway gateway,
            QuoteAuthorization authorization,
            QuoteRequestRegistry registry) {
        this.gateway = gateway;
        this.authorization = authorization;
        this.registry = registry;
    }

    ShippingQuoteReply getQuote(
            ShippingQuoteRequest request,
            AuthenticatedQuoteActor actor) {

        authorization.requireAllowed(actor, request);
        registry.verifyLogicalIdentity(actor, request);

        ShippingQuoteReply reply = gateway.quote(
                request,
                actor.tenantId(),
                request.requestId());

        if (reply == null) {
            throw new IllegalStateException("NO_REPLY_RECEIVED");
        }
        if (!request.requestId().equals(reply.requestId())) {
            throw new IllegalStateException("WRONG_REQUEST_REPLY");
        }
        if (reply.contractVersion() != 1) {
            throw new IllegalStateException(
                    "UNSUPPORTED_REPLY_VERSION");
        }
        return reply;
    }
}
~~~

If the Gateway fails to return a reply on time, `getQuote` may throw an exception or receive a result depending on timeout configuration; this example only checks **an actually received reply**. `reply` may need a null check depending on Gateway version/return contract so it does not raise an uninformative `NullPointerException`.

### 18.3. Remote Service Must Also Authorize

Do not rely solely on the internal caller having checked permissions. When messages cross a broker/network, the remote side may be called by another producer. Remote ingress needs authentication, tenant binding, and proper authorization; an application header sent by a producer is not authorization by itself.

### 18.4. Never Put Secrets in Replies

Replies can enter logs, caches, or UIs. Only return data needed by consumers: `requestId`, quote, validity, safe error code. Never echo JWT tokens, cookies, mTLS private material, or raw stack traces.

## 19. Retry and Idempotency for Side-Effecting RPCs

In the pure pricing example, re-calling may produce no side effects. When applying RPI to **reserveInventory**, **chargePayment**, **bookShipment**, or **createOrder**, a timeout risks resending an already executed operation.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant S as Remote service
    participant D as Database
    C->>S: Reserve(operationId=op-91)
    S->>D: Commit reservation
    D-->>S: Committed
    Note over S,C: Reply lost / connection reset
    C->>C: Timeout / UNKNOWN
    C->>S: Retry same operationId=op-91
    S->>D: Find committed result by operationId
    D-->>S: Existing reservation receipt
    S-->>C: Same logical result
~~~

### 19.1. Distinguishing requestId and operationId

For a read-only quote, `requestId` suffices to identify the query. For side-effecting commands, you need **`operationId`/`idempotencyKey`** scoped by `tenant+producer+operationType`. You may set `operationId=requestId` **if the contract specifies and guarantees uniqueness properly**; never assume all RPC requests sharing a `businessCorrelationKey` are one operation.

### 19.2. A Durable Ledger

~~~sql
CREATE TABLE rpc_operation_inbox (
    tenant_id VARCHAR(48) NOT NULL,
    producer_id VARCHAR(64) NOT NULL,
    operation_type VARCHAR(48) NOT NULL,
    operation_id VARCHAR(96) NOT NULL,
    request_digest VARCHAR(128) NOT NULL,
    contract_version INTEGER NOT NULL,
    state VARCHAR(24) NOT NULL,
    result_reference VARCHAR(160),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (
        tenant_id, producer_id, operation_type, operation_id)
);

CREATE INDEX rpc_operation_inbox_state_idx
    ON rpc_operation_inbox (state);
~~~

**Identity scope must follow the contract source.** If `operationId` is globally unique across the system, you can simplify; if only unique per producer, never omit `producer_id`.

### 19.3. Same Key, Different Payload = Conflict

An idempotency key reused with a different request digest is not a harmless redelivery. Return conflict/quarantine, require the producer to issue a new `operationId` or follow a conditional revision contract. Never overwrite the old operation and return `QUOTED`/`ACCEPTED` as if nothing happened.

### 19.4. Processing States

~~~text
RECEIVED
   |
   v
DISPATCH_PENDING
   |
   v
EXECUTING
   |
   +--> EFFECT_COMMITTED --> COMPLETED
   |
   +--> FAILED_TERMINAL
   |
   +--> NEEDS_RECONCILIATION
~~~

On retry, only skip execution when the state conclusively establishes the outcome; `RECEIVED` does not mean the effect already happened.

### 19.5. Bounded Retries and Classification Policy

| Error | Retry? | Condition |
| --- | --- | --- |
| Schema/version unsupported | Do not retry identical payload indefinitely | Fix contract/producers |
| Authorization denied | Do not auto-retry | Audit/fix permissions |
| Conclusive business rejection | Do not retry like a network error | Wait for a new request |
| Transient connection reset | Possibly | Stable `operationId`, bounded backoff |
| Rate limited | Per `Retry-After`/deadline if present | Bounded attempts |
| Timeout after sending side-effecting command | Requires reconcile/idempotent retry | Never create duplicate effects |
| Reply `requestId` mismatch | Do not accept reply | Quarantine/security alert |

Never use one blanket retry advice for all exceptions when both permanent data errors and transient infrastructure errors can occur.

## 20. Outbox, Inbox, and Crash Windows

Idempotency is not merely a unique index. Writing `SEEN` and crashing before dispatch can leave a message **never processed**:

~~~text
1. INSERT inbox(op-91, state=SEEN)
2. COMMIT
3. Crash before remote side effect
4. Request is redelivered
5. "op-91 exists" -> drop
6. Effect never happens
~~~

Options:

- **Transactional outbox:** record intake state and outbound task in the same DB transaction; a worker dispatches the task and updates state with recovery.
- **Inbox state machine:** claim operation, advance states, with lease/reaper to recover in-flight work after crashes.
- **Idempotent external provider API:** send a stable provider idempotency key; query status before retrying when outcomes are unknown.
- **Compensation/Saga:** when multiple remote effects lack a shared transaction, define compensating actions, triggers, and limits.

Never call an RPC method assuming an **exactly-once distributed transaction**. Spring Integration provides message delivery, retries, persistence, and advice, yet the application must still define **business effect semantics**.

### 20.1. Retrying a Request Must Not Change Its Meaning

If quote `rateVersion` changes after the caller timed out, re-executing the same `requestId` could yield a different price. If the contract requires replaying the same `operationId` to return the same result, store the **reply snapshot/rate version** on first completion; never recompute with new rules and call it a normal replay.

### 20.2. Rebuilding Projections Differs from Replaying Side Effects

Replaying historical requests to rebuild reporting/read models must not re-issue charges/reservations/bookings. Separate processing modes or use an immutable event log + idempotency ledger; any re-execution with side effects requires explicit authorization and policy.

## 21. Shifting a Contract from Synchronous to Asynchronous

If a remote operation takes minutes or spans multiple downstream systems, do not stretch a Gateway invocation indefinitely. One option is **request → accepted receipt → completion event**:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as API / Gateway
    participant W as Durable workflow
    participant P as External provider
    C->>A: POST command, operationId=op-91
    A->>W: Persist command / outbox
    A-->>C: 202 Accepted, operationId
    W->>P: Execute with idempotency key
    P-->>W: Completion callback / result
    W->>W: Verify identity, record terminal outcome
    C->>A: GET /operations/op-91
    A-->>C: COMPLETED / REJECTED / PENDING
~~~

### 21.1. Accepted Does Not Mean Completed

~~~json
{
  "contractVersion": 1,
  "operationId": "op-91",
  "outcome": "ACCEPTED",
  "statusRef": "operations/op-91",
  "acceptedAt": "2026-11-21T03:00:00Z"
}
~~~

The contract must state **how far persistence succeeded** when returning `ACCEPTED`: only received in memory, broker accepted, or outbox transaction committed? If the system could crash and lose the command right after returning 202, `ACCEPTED` is misleading.

### 21.2. Completion Events Must Guard Against Duplicates and Spoofed Sources

~~~json
{
  "contractVersion": 1,
  "operationId": "op-91",
  "eventId": "evt-complete-op-91-v1",
  "outcome": "COMPLETED",
  "completedAt": "2026-11-21T03:04:00Z"
}
~~~

Callbacks need authentication/signatures or broker ACLs, tenant + operation ownership verification, and deduplication by event/operation identity. Never accept a completion just because the sender knows `op-91`.

### 21.3. Poll or Subscribe?

- **Poll status:** simple for users querying status; needs rate limits, TTL, and access control.
- **Webhook/callback:** low latency, but requires auth, retries, dedup, replay protection, and webhook delivery policies.
- **Message consumer:** fits backend systems sharing a broker/stream; still needs persisted offsets/inbox.

Do not force clients to fetch an arbitrary `statusUrl` supplied by an untrusted remote producer; if a backend fetches arbitrary URLs, SSRF risks arise. Use a trusted service registry or ID-based routing for status queries.

### 21.4. When to Use Scatter-Gather?

If a shipment needs quotes from three providers to pick the best rate, use Scatter-Gather and an Aggregator. The contract needs:

- A correlation key bound to `tenant+shipment+workflow epoch`.
- An expected provider set or manifest.
- One **terminal result** per provider operation—do not count retries as new results.
- A release policy when enough unique outcomes arrive or the deadline hits.
- Policies for **partial results** and late arrivals.
- A single final reply or async completion event with an explicit schema.

A Gateway waiting for one result will not assemble three replies with the right business rules on its own; the Aggregator must fulfill that contract.

## 22. Error Handling on Spring Integration Channels

Failures in a request/reply contract can happen at multiple points:

~~~mermaid
flowchart TD
    A["Gateway invocation"] --> B{"Argument binding + send"}
    B -->|"Invalid / no subscriber"| E1["Invocation / send error"]
    B -->|"Dispatched"| C{"Handler"}
    C -->|"Business reject"| R["Typed ShippingQuoteRejected"]
    C -->|"Validation/security exception"| E2["Fail + audit"]
    C -->|"Transient infrastructure"| E3["Retry / errorChannel / recover"]
    C -->|"Success"| O["ShippingQuoteSuccess"]
    O --> D{"Reply path"}
    R --> D
    D -->|"On time"| G["Gateway return"]
    D -->|"Late / missing"| E4["Timeout / UNKNOWN"]
~~~

### 22.1. Errors on DirectChannel

In the demo setup, `rpcQuoteRequests` is a **DirectChannel**. Handlers usually run on the caller thread, and exceptions can propagate back to the Gateway, wrapped by Spring Integration via `MessagingException`.

Throwing an exception from a handler does not automatically send a `Message` to `errorChannel` and return `ShippingQuoteRejected`; error routing depends on topology/advice/error configuration.

### 22.2. Errors on ExecutorChannel/Poller

When switching to an `ExecutorChannel`, worker thread, or poller, exceptions can produce an **`ErrorMessage`** sent to an appropriate error channel. `ErrorMessage` carries a `Throwable` (possibly referencing `failedMessage`), **not** a normal `ShippingQuoteReply` payload.

The error flow must recover `requestId`, tenant, and `operationId` from **trusted sources/persisted state**, classify the error, and decide reply/retry/recovery. Never read `errorMessage.getPayload()` as `ShippingQuoteRequest` without type checks.

### 22.3. When to Convert an Error into a Typed Reply?

Only when the remote has proof of a **conclusive business outcome** and the contract defines a matching code. For example, `SERVICE_LEVEL_UNAVAILABLE` is a business rejection. However:

~~~text
SQLException
SocketTimeoutException
ConnectionReset
UnknownCommitState
~~~

do not automatically become `QUOTED` or `REJECTED`. Known technical failures can return a structured technical fault per contract; timeouts with no reply should leave the caller with an exception/`UNKNOWN`.

### 22.4. errorChannel Is Not a Durable Dead-Letter Queue

`errorChannel` is an error-routing concept in Spring Integration. To handle failures across restarts, configure persistent transport/storage, retry metadata, ownership, and retention; an in-memory `PublishSubscribeChannel` or `QueueChannel` is not durable by itself.

### 22.5. Distinguishing Retryable from Safe-to-Retry

An HTTP 503/`SocketTimeout` may be transient, yet if `chargePayment` already committed before the reply was lost, **sending a new `operationId`** is unsafe. "Is the failure recoverable?" and "Is the operation safe to retry?" are two separate questions.

## 23. Security: Request/Reply Contracts Must Protect Both Directions

An RPC-like flow carries risks of forged requests, forged replies, correlation collisions, and cross-tenant data leaks.

### 23.1. At the Request Side

1. Authenticate caller/producer.
2. Bind tenant and principal from a trusted source.
3. Authorize operation + `shipmentId` + workflow epoch.
4. Validate input schema, sizes, enums, ranges, and currency.
5. Bind `requestId`/`operationId` to the verified payload and tenant.
6. Build the Spring `Message` with a **header allowlist**.
7. Bound timeouts, rates, queue capacities, and max message size.

Never use a client-supplied `tenantId` JSON field as proof of authentication.

### 23.2. At the Reply Side

1. Verify remote reply source/certificate/broker ACL.
2. Decode reply per negotiated `schemaVersion`.
3. Compare `requestId` and, when needed, tenant/operation binding.
4. Validate reply outcome fields and types.
5. Block replays/conflicting terminal outcomes.
6. Never return tenant A's reply to tenant B's caller.
7. Sanitize technical fault messages.

### 23.3. Correlation ID Is Not a Secret

A `requestId`/`correlationKey` may appear in logs or be guessable. It must **never** be used as a secret token or substitute for authentication. On status endpoints, verify the actor is authorized for the `operationId`; do not merely check that the requester knows the ID.

### 23.4. Never Copy External Framework Control Headers

Headers like `replyChannel`, `errorChannel`, and `routingSlip` can alter message routing. External producers must never dictate internal destinations. Ingress must construct a fresh `Message` or filter headers against an allowlist; selected business metadata is trusted only after verification.

### 23.5. Never Deserialize Arbitrary Class Names

A client-sent wire field like `"javaClass":"com.example.RemoteCommand"` must never trigger arbitrary polymorphic deserialization. Select DTOs by **operation + contractVersion** from an allowlist/schema registry; bound depth/size and validate contents after parsing.

### 23.6. Never Log Raw Sensitive Requests/Replies

Even a `ShippingQuoteRequest` can contain a customer address in a real application. Logs should record `requestRef`, stage, outcome, and error code; raw payloads/quarantine need access control, encryption, retention, and auditing.

## 24. Observability for Request/Reply Contracts

A generic `RPC_FAILED` error cannot tell whether the request failed to send, remote failed processing, or the reply was lost. Separate the stages.

| Metric | Meaning | Bounded Labels |
| --- | --- | --- |
| `rpc_requests_total` | Requests started | operation, version |
| `rpc_dispatch_failed_total` | Failures sending to channel/transport | operation, reason |
| `rpc_request_validation_failed_total` | Invalid request schema/identity | reasonCode |
| `rpc_business_rejected_total` | Server returned business rejection | code |
| `rpc_success_total` | Valid `QUOTED` received | operation, version |
| `rpc_reply_timeout_total` | Caller missed reply deadline | operation |
| `rpc_reply_mismatch_total` | Reply `requestId`/version mismatch | reasonCode |
| `rpc_reply_schema_failed_total` | Reply failed decode/validation | version |
| `rpc_inflight_requests` | Requests currently waiting | operation |
| `rpc_request_duration_seconds` | Latency from caller to reply | operation |
| `rpc_pending_operations` | Non-terminal operations | state |
| `rpc_idempotency_conflict_total` | Same key, different payload | operation |
| `rpc_retry_attempt_total` | Transient retries | reasonClass |
| `rpc_late_reply_total` | Replies arriving after deadline | operation |

Never use `requestId`, `shipmentId`, `tenantId`, or `traceId` as **metric labels** due to high cardinality and potential data exposure. Use structured logs/traces with proper search and retention.

### 24.1. Structured Log on Dispatch

~~~json
{
  "component": "ShippingQuoteGateway",
  "stage": "REQUEST_DISPATCH",
  "operation": "QUOTE_SHIPPING",
  "contractVersion": 1,
  "requestRef": "req-quote-00091",
  "outcome": "SENT"
}
~~~

### 24.2. Structured Log on Reply

~~~json
{
  "component": "QuoteRpcHandler",
  "stage": "REPLY",
  "contractVersion": 1,
  "requestRef": "req-quote-00091",
  "replyType": "QUOTED",
  "rateVersion": "rate-demo-v1",
  "outcome": "COMPLETED"
}
~~~

### 24.3. Log When No Reply Arrives

~~~json
{
  "component": "ShippingQuoteGateway",
  "stage": "REPLY_WAIT",
  "requestRef": "req-quote-00091",
  "reason": "TIMEOUT",
  "businessOutcome": "UNKNOWN"
}
~~~

These examples are **application-defined logs**, not formats auto-generated by Spring Integration. If the Gateway times out before the handler runs, handler-only logging will miss that request; instrument caller, adapter, and remote alike.

### 24.4. SLOs/Alerts Must Tie to Outcomes

A "99% HTTP 200" SLO can hide failures if the API always returns 200 with `outcome=REJECTED` or `outcome=UNKNOWN`. Measure:

- Rate of `QUOTED` across valid requests.
- Rate of business rejections by code (not counted as availability outages).
- Timeouts/lost replies per transport.
- Backlog of pending/needs-reconciliation operations.
- p95/p99 latency and deadline violations.
- Event ID conflicts, duplicate-effect preventions, and late replies.

## 25. Unit Tests: Request/Reply Invariants and Business Semantics

Unit tests for `QuoteDecisionService` should assert both **values** and **outcome types**—not just non-null replies.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Currency;

import org.junit.jupiter.api.Test;

class QuoteDecisionServiceTest {

    private final Clock fixedClock = Clock.fixed(
            Instant.parse("2026-11-21T03:00:00Z"),
            ZoneOffset.UTC);
    private final QuoteDecisionService service =
            new QuoteDecisionService(fixedClock);

    private ShippingQuoteRequest request(
            String requestId,
            ShippingServiceLevel level,
            int parcelCount) {
        return new ShippingQuoteRequest(
                1, requestId, "SHIP-901",
                level, parcelCount, "VND");
    }

    @Test
    void expressRequestProducesTypedSuccessfulReply() {
        ShippingQuoteRequest input = request(
                "req-quote-901",
                ShippingServiceLevel.EXPRESS, 2);

        ShippingQuoteReply reply = service.decide(input);
        assertInstanceOf(ShippingQuoteSuccess.class, reply);

        ShippingQuoteSuccess success = (ShippingQuoteSuccess) reply;
        assertEquals(1, success.contractVersion());
        assertEquals(input.requestId(), success.requestId());
        assertEquals(input.shipmentId(), success.shipmentId());
        assertEquals(new BigDecimal("160000"),
                success.price().amount());
        assertEquals(Currency.getInstance("VND"),
                success.price().currency());
        assertEquals("rate-demo-v1", success.rateVersion());
        assertEquals(Instant.parse("2026-11-21T03:10:00Z"),
                success.validUntil());
    }

    @Test
    void standardRequestHasDifferentPriceButSameSchema() {
        ShippingQuoteReply reply = service.decide(
                request("req-standard-901",
                        ShippingServiceLevel.STANDARD, 2));

        ShippingQuoteSuccess success =
                assertInstanceOf(ShippingQuoteSuccess.class, reply);
        assertEquals(new BigDecimal("60000"),
                success.price().amount());
        assertEquals(1, success.contractVersion());
    }

    @Test
    void businessRuleCanRejectWithoutThrowingTransportError() {
        ShippingQuoteRequest input = request(
                "req-too-many-parcels",
                ShippingServiceLevel.EXPRESS, 21);

        ShippingQuoteReply reply = service.decide(input);

        ShippingQuoteRejected rejected =
                assertInstanceOf(ShippingQuoteRejected.class, reply);
        assertEquals(input.requestId(), rejected.requestId());
        assertEquals("SERVICE_LEVEL_UNAVAILABLE",
                rejected.code());
        assertFalse(rejected.retryable());
    }

    @Test
    void invalidRequestVersionIsRejectedBeforeHandler() {
        assertThrows(IllegalArgumentException.class, () ->
                new ShippingQuoteRequest(
                        99, "req-901", "SHIP-901",
                        ShippingServiceLevel.STANDARD, 2, "VND"));
    }

    @Test
    void invalidParcelCountIsRejected() {
        assertThrows(IllegalArgumentException.class, () ->
                request(
                        "req-invalid",
                        ShippingServiceLevel.STANDARD, 0));
    }

    @Test
    void nonVndQuoteAmountIsNotSilentlyAccepted() {
        assertThrows(IllegalArgumentException.class, () ->
                new QuoteMoney(
                        new BigDecimal("12.35"),
                        Currency.getInstance("USD")));
    }

    @Test
    void vndFractionIsNotSilentlyRounded() {
        assertThrows(ArithmeticException.class, () ->
                new QuoteMoney(
                        new BigDecimal("1200.25"),
                        Currency.getInstance("VND")));
    }

    @Test
    void sameInputAndClockProduceSameBusinessReply() {
        ShippingQuoteRequest input = request(
                "req-repeat",
                ShippingServiceLevel.EXPRESS, 2);
        assertEquals(service.decide(input), service.decide(input));
    }
}
~~~

The last test uses a **fixed Clock**. With a real system clock, `validUntil` varies between calls, proving business logic does not automatically provide a **persisted exactly-once reply snapshot**. If the contract requires replaying the same `requestId` to return the same `validUntil`, persist the committed result by idempotency key.

### 25.1. Testing Header and requestId Matching Without Annotation Resolvers

You can invoke the handler directly:

~~~java
@Test
void handlerRejectsMismatchedRequestIdHeader() {
    QuoteRpcHandler handler = new QuoteRpcHandler(
            new QuoteDecisionService(fixedClock));
    ShippingQuoteRequest input = request(
            "req-correct",
            ShippingServiceLevel.STANDARD, 1);

    assertThrows(SecurityException.class, () ->
            handler.handle(
                    input,
                    "tenant-a",
                    "req-different"));
}
~~~

This is a **Java unit test**; the framework has not resolved `@Header`. To prove `MessageHeaders` map to Java parameters and replies return to the Gateway, run an integration test with a Spring context.

### 25.2. Testing requestId Across Multiple Tenants

If `requestId` is unique per producer/tenant scope, the same `requestId` string in two tenants represents two distinct logical requests. Ledgers and authorization must use corresponding namespaces. Never use a bare `requestId` string as a global key unless the contract guarantees global uniqueness.

## 26. Integration Test: Real Gateway Proxy and Service Activator

The test below does not manually construct a Spring `Message`; it calls the **Gateway proxy** and lets Spring Integration build request headers, dispatch to `DirectChannel`, and receive the reply from `QuoteRpcHandler`.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(QuoteRpcConfig.class)
class QuoteRpcIntegrationTest {

    @Autowired
    ShippingQuoteGateway gateway;

    private ShippingQuoteRequest request(
            String id,
            ShippingServiceLevel level,
            int parcels) {
        return new ShippingQuoteRequest(
                1, id, "SHIP-901", level, parcels, "VND");
    }

    @Test
    void gatewayMapsPayloadAndRequestIdHeaderToHandler() {
        ShippingQuoteRequest command = request(
                "req-int-1", ShippingServiceLevel.EXPRESS, 2);

        ShippingQuoteReply reply = gateway.quote(
                command, "tenant-a", command.requestId());

        ShippingQuoteSuccess success =
                assertInstanceOf(ShippingQuoteSuccess.class, reply);
        assertEquals(command.requestId(), success.requestId());
        assertEquals("SHIP-901", success.shipmentId());
        assertEquals(new BigDecimal("160000"),
                success.price().amount());
        assertEquals("rate-demo-v1", success.rateVersion());
        assertEquals(Instant.parse("2026-11-21T03:10:00Z"),
                success.validUntil());
    }

    @Test
    void gatewayReturnsTypedBusinessRejection() {
        ShippingQuoteRequest command = request(
                "req-int-2", ShippingServiceLevel.EXPRESS, 21);

        ShippingQuoteReply reply = gateway.quote(
                command, "tenant-a", command.requestId());

        ShippingQuoteRejected rejected =
                assertInstanceOf(ShippingQuoteRejected.class, reply);
        assertEquals("req-int-2", rejected.requestId());
        assertEquals("SERVICE_LEVEL_UNAVAILABLE",
                rejected.code());
        assertFalse(rejected.retryable());
    }

    @Test
    void separateRequestsRetainTheirOwnIdentities() {
        ShippingQuoteRequest first = request(
                "req-int-A", ShippingServiceLevel.STANDARD, 1);
        ShippingQuoteRequest second = request(
                "req-int-B", ShippingServiceLevel.EXPRESS, 3);

        ShippingQuoteReply replyA = gateway.quote(
                first, "tenant-a", first.requestId());
        ShippingQuoteReply replyB = gateway.quote(
                second, "tenant-a", second.requestId());

        assertEquals("req-int-A", replyA.requestId());
        assertEquals("req-int-B", replyB.requestId());
        assertNotEquals(replyA.requestId(), replyB.requestId());
    }

    @Test
    void requestIdHeaderMismatchIsRejected() {
        ShippingQuoteRequest command = request(
                "req-int-3", ShippingServiceLevel.STANDARD, 1);

        // Outermost exception may be MessagingException.
        assertThrows(RuntimeException.class, () ->
                gateway.quote(
                        command,
                        "tenant-a",
                        "req-forged"));
    }

    @Test
    void missingTenantIsNotAccepted() {
        ShippingQuoteRequest command = request(
                "req-int-4", ShippingServiceLevel.STANDARD, 1);

        assertThrows(RuntimeException.class, () ->
                gateway.quote(
                        command,
                        null,
                        command.requestId()));
    }
}
~~~

### 26.1. What the Integration Test Proves

- Spring context registers the Gateway proxy via `@IntegrationComponentScan`.
- `@Payload` and `@Header` on the Gateway map Java arguments into a `Message`.
- The Service Activator receives the typed request and corresponding headers.
- `QUOTED`/`REJECTED` replies return to the right synchronous Gateway invocation.
- `requestId` mismatch is not returned as a success.

### 26.2. What the Integration Test Does Not Prove

- HTTP/JMS/AMQP network converters/headers work properly.
- Reply correlation across multiple instances over a broker.
- Authorization with JWT/mTLS/ACL or real shipment ownership.
- Durable idempotency/outbox across crashes.
- Timeouts/cancellation when the remote hangs.
- Side-effecting business operations execute exactly once.

**This is an in-JVM Spring runtime contract test**, not a substitute for end-to-end tests with real transport and database.

### 26.3. Notes When Running Tests by Version

In modern Spring Integration releases, `@MessagingGateway`, `@Gateway`, `@ServiceActivator`, `@EnableIntegration`, and `@IntegrationComponentScan` are standard APIs. When assembling snippets into a real module, place interfaces and configs in the proper packages, use compatible Spring Test/JUnit dependencies, and verify external converter configurations. This lesson belongs to STEP 4 and has not yet run Content QA/Gradle.

## 27. Negative Tests: Contracts Must Fail Clearly Before Causing Side Effects

An RPC-like system needs more **negative tests** than happy-path tests. The worst bugs occur when responses match the wrong request, tenants get mixed up, unknown schemas are treated as success, or retries duplicate effects.

### 27.1. Minimum Test Matrix

| Case | Scenario | Outcome to Assert |
| --- | --- | --- |
| **Missing requestId** | Request lacks logical identity | Reject before dispatch |
| **Unsupported version** | `contractVersion=99` | Reject/unsupported schema |
| **Invalid parcelCount** | 0 or 1001 | Validation error |
| **Unknown currency** | USD in VND-only demo | Never auto-convert |
| **Unknown service level** | Unsupported `DRONE` enum | Parse/validation reject |
| **Header/request mismatch** | `businessRequestId` differs from `requestId` | Exception/reject |
| **Tenant spoofing** | Caller self-declares `tenant-admin` | Facade authorization reject |
| **Wrong reply ID** | Reply `requestId` differs from request | Reject, do not return to caller |
| **Wrong reply version** | v2 reply to v1-only client | Reject/compatibility path |
| **Invalid money precision** | 12.50 VND under no-fractional policy | Reject, never round |
| **No responder** | Handler produces no reply | Reply timeout/technical failure |
| **Late reply** | Reply arrives after deadline | Never attach to another invocation |
| **Duplicate request** | Same `operationId`, identical payload | Do not create a new side effect |
| **Identity conflict** | Same `operationId`, different payload | `ID_CONFLICT` |
| **Broker redelivery** | Consumer reprocesses after crash | Recovery/idempotent |
| **Transport header loss** | `businessRequestId` dropped by JMS mapper | Caught by contract test |
| **Invalid error code** | Error code outside allowlist | Unknown error policy, never fake `QUOTED` |
| **Unauthenticated callback** | Outsider knows `operationId` | Reject |
| **Expired quote** | `validUntil` has passed | Do not use stale price |
| **Cross-tenant reply** | Tenant B receives Tenant A's result | Security failure |

### 27.2. Testing Wrong requestId Reply at the Facade

Testing the application layer in isolation, you can stub the Gateway with a lambda because `ShippingQuoteGateway` has a single abstract method in the example:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class QuoteApplicationFacadeTest {

    @Test
    void rejectsReplyForAnotherRequest() {
        ShippingQuoteGateway wrongGateway =
                (request, tenant, businessRequestId) ->
                        new ShippingQuoteRejected(
                                1,
                                "req-other",
                                "SERVICE_LEVEL_UNAVAILABLE",
                                false,
                                "Not available");

        QuoteAuthorization allowDemo =
                (actor, request) -> { /* test-only */ };
        QuoteRequestRegistry allowIdentity =
                (actor, request) -> { /* test-only */ };

        QuoteApplicationFacade facade = new QuoteApplicationFacade(
                wrongGateway, allowDemo, allowIdentity);

        ShippingQuoteRequest request = new ShippingQuoteRequest(
                1, "req-original", "SHIP-901",
                ShippingServiceLevel.STANDARD, 1, "VND");

        assertThrows(IllegalStateException.class, () ->
                facade.getQuote(
                        request,
                        new AuthenticatedQuoteActor(
                                "principal-1", "tenant-a")));
    }

    @Test
    void authorizationRunsBeforeSendingMessage() {
        final int[] invoked = {0};
        ShippingQuoteGateway gateway =
                (request, tenant, id) -> {
                    invoked[0]++;
                    return new ShippingQuoteRejected(
                            1, request.requestId(),
                            "SERVICE_LEVEL_UNAVAILABLE",
                            false, "Not available");
                };
        QuoteAuthorization deny =
                (actor, request) -> {
                    throw new SecurityException("SHIPMENT_ACCESS_DENIED");
                };
        QuoteRequestRegistry registry =
                (actor, request) -> { /* test-only */ };
        QuoteApplicationFacade facade =
                new QuoteApplicationFacade(gateway, deny, registry);

        ShippingQuoteRequest request = new ShippingQuoteRequest(
                1, "req-auth", "SHIP-901",
                ShippingServiceLevel.STANDARD, 1, "VND");

        assertThrows(SecurityException.class, () ->
                facade.getQuote(
                        request,
                        new AuthenticatedQuoteActor(
                                "principal-2", "tenant-b")));
        assertEquals(0, invoked[0]);
    }
}
~~~

**Warning:** the two lambdas `allowDemo` and `allowIdentity` are test-only stubs; never copy them as real authorization. Production must check permissions from an identity provider/registry, including tenant ownership and operation scope.

### 27.3. Testing Timeouts Matching Channel Semantics

A test without a handler may raise a send failure or reply timeout depending on the channel. **Never write tests assuming every topology throws the same Gateway timeout exception.** Create dedicated test configurations per case:

1. **RequestChannel with no subscriber** → verify dispatch error.
2. **Consumer receives Message but sends no reply** → verify reply wait/timeout.
3. **DirectChannel handler blocks** → verify caller hold time; do not assume `replyTimeout` interrupts the handler.
4. **ExecutorChannel handler is slow** → verify receive timeout and late-reply handling.
5. **Transport resets after side effect** → verify reconciliation rather than generating a new `operationId`.

Keep timeouts short in tests and use `CountDownLatch`, fake Clocks, or controlled executors where appropriate to avoid flaky tests relying on `Thread.sleep()`.

### 27.4. Testing Error Taxonomy

Separate at least:

- Unparseable request → schema/validation failure.
- Header/requestId mismatch → contract/identity failure.
- Missing tenant authorization → authorization failure.
- Service cannot fulfill request → typed `ShippingQuoteRejected`.
- Remote timeout → technical `UNKNOWN`.
- Reply wrong `requestId` → correlation mismatch.
- Side effect committed but reply lost → reconcile/idempotent read.

If all of these emit the same string `"ERROR"`, consumers cannot tell when retrying is safe.

## 28. Wire Contract Tests: Never Serialize Domain Records by Guesswork

Domain Java records have convenient structures that do not necessarily match published JSON schemas. For instance, `QuoteMoney` is a Java record containing `BigDecimal` and `Currency`; default serialization may produce a number or string depending on the converter, whereas the example contract requires a **decimal string**.

### 28.1. Creating Explicit Wire DTOs

~~~java
record QuoteMoneyWire(
        String amount,
        String currencyCode) {
}

record QuoteSuccessBodyWire(
        String shipmentId,
        QuoteMoneyWire money,
        String rateVersion,
        String validUntil) {
}

record QuoteSuccessWire(
        int contractVersion,
        String requestId,
        String outcome,
        QuoteSuccessBodyWire result) {

    static QuoteSuccessWire from(ShippingQuoteSuccess domain) {
        QuoteMoney money = domain.price();
        return new QuoteSuccessWire(
                domain.contractVersion(),
                domain.requestId(),
                "QUOTED",
                new QuoteSuccessBodyWire(
                        domain.shipmentId(),
                        new QuoteMoneyWire(
                                money.amount().toPlainString(),
                                money.currency().getCurrencyCode()),
                        domain.rateVersion(),
                        domain.validUntil().toString()));
    }
}
~~~

This new wire schema has `result.money.amount` instead of `result.amount` in section 4's JSON example. If section 4's JSON has **already been published**, you must not silently alter field paths. Two valid choices:

- Preserve section 4's contract by changing `QuoteSuccessBodyWire` to carry `amount` and `currencyCode` directly.
- Or publish schema **v2** with a nested money object and a migration policy.

To keep the lesson's examples **consistent with v1**, we choose **flat result fields** in the next step.

### 28.2. Flat Result Wire DTO Matching Schema v1

~~~java
record QuoteSuccessResultV1(
        String shipmentId,
        String amount,
        String currencyCode,
        String rateVersion,
        String validUntil) {
}

record QuoteSuccessWireV1(
        int contractVersion,
        String requestId,
        String outcome,
        QuoteSuccessResultV1 result) {

    static QuoteSuccessWireV1 from(ShippingQuoteSuccess domain) {
        return new QuoteSuccessWireV1(
                1,
                domain.requestId(),
                "QUOTED",
                new QuoteSuccessResultV1(
                        domain.shipmentId(),
                        domain.price().amount().toPlainString(),
                        domain.price().currency().getCurrencyCode(),
                        domain.rateVersion(),
                        domain.validUntil().toString()));
    }
}
~~~

**Use `QuoteSuccessWireV1` for this lesson's contract**, whereas nested `QuoteSuccessWire` in section 28.1 is an **incompatible, non-equivalent schema**. Comparing the two exposes a breaking change disguised as a harmless DTO layout choice.

### 28.3. Testing the JSON Contract with Jackson

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Currency;
import org.junit.jupiter.api.Test;

class QuoteWireContractTest {

    @Test
    void successReplyMatchesPublishedVersionOneShape()
            throws Exception {

        ShippingQuoteSuccess domain = new ShippingQuoteSuccess(
                1,
                "req-quote-00091",
                "SHIP-901",
                new QuoteMoney(
                        new BigDecimal("160000"),
                        Currency.getInstance("VND")),
                "rate-demo-v1",
                Instant.parse("2026-11-21T03:10:00Z"));

        ObjectMapper mapper = new ObjectMapper();
        QuoteSuccessWireV1 wire = QuoteSuccessWireV1.from(domain);
        JsonNode root = mapper.readTree(
                mapper.writeValueAsBytes(wire));

        assertEquals(1, root.path("contractVersion").asInt());
        assertEquals("req-quote-00091",
                root.path("requestId").asText());
        assertEquals("QUOTED", root.path("outcome").asText());
        assertEquals("SHIP-901",
                root.path("result").path("shipmentId").asText());
        assertEquals("160000",
                root.path("result").path("amount").asText());
        assertEquals("VND",
                root.path("result").path("currencyCode").asText());
        assertEquals("2026-11-21T03:10:00Z",
                root.path("result").path("validUntil").asText());
        assertTrue(root.path("error").isMissingNode());
    }
}
~~~

This test uses a **wire DTO with a `String` `validUntil`**, so Jackson's `JavaTimeModule` is not needed to serialize an `Instant` directly. If you serialize domain records containing `Instant`, configure the Java Time module accordingly.

### 28.4. Selecting the Right Reply Variant When Decoding

Upon receiving JSON:

1. Read `contractVersion` and `outcome` against an allowlist.
2. If `QUOTED`, validate `result` has all required fields; no `error`.
3. If `REJECTED`, validate `error` has `code`/`retryable`/`safeMessage`; no success `result`.
4. If `outcome` is unsupported, return an unsupported-reply error; **never default to `QUOTED`**.
5. Verify `requestId` and sender identity before returning to the Gateway caller.

Never enable deserialization based on an arbitrary `@class` field from remote; use the published schema discriminator.

### 28.5. Consumer-Driven Contracts

With multiple consumers, each client can verify the fields it relies on: `requestId`, `outcome`, price precision, error codes, and timestamps. Producer contract tests must run in CI whenever schemas change, even when only a `MessageConverter`/`HeaderMapper` changed while Java DTOs stayed intact.

## 29. Runbook: Caller Timed Out, Unknown Whether Remote Processed It

**Scenario:** a Java caller invokes `quoteGateway.quote(...)`, waits, and hits a timeout. Remote metrics show sometimes requests were processed and sometimes not. If this were a reserve/charge command, blind retrying could duplicate effects.

### Step 1 — Verify Request Contract at the Caller

Collect:

~~~text
operation = QUOTE_SHIPPING
contractVersion = 1
requestId = req-quote-00091
tenant = tenant-a (verified)
shipmentId = SHIP-901
serviceLevel = EXPRESS
deadline = <the actual application deadline>
~~~

Do not log raw addresses/payment payloads or credentials. Check whether `requestId` remained stable across attempts and was not altered when the Gateway proxy was re-invoked.

### Step 2 — Determine Whether the Request Reached the Channel

Distinguish:

- Gateway mapping/validation error before sending.
- Request channel had no subscriber.
- Queue/executor full or send timeout.
- Outbound adapter received the message and started the network call.

If the failure happened **before sending**, the remote likely never saw the request. If it happened after network send, you cannot conclude the operation was not processed.

### Step 3 — Check Protocol Correlation

For JMS/AMQP, check the correlation token/`ReplyTo` at the **transport layer**; for HTTP, check request/response traces at the connector; for Java Gateway, check the temporary `replyChannel` invocation. Do not confuse these tokens with `businessRequestId`.

### Step 4 — Check Remote Inbox/Operation State

~~~text
requestId = req-quote-00091
operationId = op-91 (if side-effecting command)

Remote state:
  RECEIVED / DISPATCH_PENDING / EXECUTING /
  COMPLETED / FAILED_TERMINAL / NEEDS_RECONCILIATION
~~~

- No record: may not have arrived or not yet persisted; check broker/transport.
- `RECEIVED`/`IN_PROGRESS`: must not be treated as failed; inspect worker/lease/recovery.
- `COMPLETED`: retrieve stored result, do not execute the effect a second time.
- `ID_CONFLICT`: compare payload digest/tenant/producer; investigate.
- `NEEDS_RECONCILIATION`: query provider or run recovery policy.

### Step 5 — Verify Whether the Reply Was Built Per Contract

A service may have processed and returned:

~~~json
{
  "contractVersion": 1,
  "requestId": "req-other",
  "outcome": "QUOTED",
  "result": {}
}
~~~

This reply is **invalid for the current request**: wrong `requestId`, `result` missing fields. Never deliver it to the caller just because a temporary `replyChannel` is waiting. Log correlation/schema errors and quarantine if necessary.

### Step 6 — Check the Reply Path

Check whether the handler returns a DTO or sends to a `QueueChannel` not bridged back to the Gateway. Verify whether a new `Message` dropped `replyChannel`, a `HeaderFilter` stripped correlation metadata, or a transport header mapper dropped `replyTo`/correlation tokens.

### Step 7 — Check Timeouts/Deadlines

Gateway `replyTimeout`, remote client timeout, broker TTL, and business deadline may differ. A reply arriving after Gateway timeout can still be a valid business result, but must be handled via **persistent workflow state**, never attached to a new invocation.

### Step 8 — Classify the Root Cause

| Signal | Classification |
| --- | --- |
| Invalid `contractVersion`, `parcelCount` | Data/schema |
| Tenant unauthorized | Security |
| Unsupported `serviceLevel` | Business rejection |
| DB down | Transient infrastructure |
| Connection reset after sending request | `UNKNOWN` |
| `Reply.requestId` differs from request | Correlation/contract violation |
| Operation committed, reply lost | Completed, caller uncertain |

### Step 9 — Controlled Recovery

If the operation is purely read-only, you may re-call with the same `requestId` under an appropriate rate version/expiry policy. If the operation creates side effects, check the ledger/provider using the stable `operationId` before retrying. When retrying, use the same identity and enforce attempt/deadline limits.

### Step 10 — Verify After Fixing

Run contract tests across Gateway and adapter, asserting:

~~~text
requestId in request == requestId in reply
contractVersion supported
reply is exactly one legal outcome
QUOTED has valid money/time fields
REJECTED has stable code
TIMEOUT stays UNKNOWN until reconciliation
no cross-tenant response
no duplicated business effect
~~~

## 30. Practice Project: Three RPC Operations and One Consistent Contract

Build the `OrderRemoteOperations` module with three operations, each having its own contract:

1. **GetShippingQuote:** read-only, returns a price or business rejection.
2. **ReserveInventory:** side-effecting command requiring idempotency + recovery.
3. **RequestCarrierBooking:** long-running, returns `ACCEPTED` + completion event.

~~~mermaid
flowchart TD
    C["Order Application"] --> G["Messaging Gateway façade"]
    G --> Q["GetShippingQuote"]
    G --> R["ReserveInventory"]
    G --> B["RequestCarrierBooking"]
    Q --> QQ["QUOTED / REJECTED reply"]
    R --> RR["RESERVED / REJECTED reply"]
    B --> BA["ACCEPTED receipt"]
    BA --> W["Durable booking workflow"]
    W --> EV["BOOKED / FAILED completion event"]
~~~

### 30.1. Contracts to Publish

| Operation | Request Identity | Reply/Outcomes | Mandatory Techniques |
| --- | --- | --- | --- |
| Quote | `requestId` | `QUOTED`, `REJECTED`, technical `UNKNOWN` | Versioned price, `validUntil` |
| Reserve | `operationId`/`idempotencyKey` | `RESERVED`, `REJECTED`, technical `UNKNOWN` | Unique ledger, stable side-effect identity |
| Book carrier | `operationId` | `ACCEPTED` → `BOOKED`/`FAILED` event | Outbox, status API, callback auth |

Never share a single `Reply` with uncontrolled nullable fields across all operations. You may share a **base envelope** for `requestId`/version/trace, while each operation defines typed results and clear error taxonomy.

### 30.2. Sample Inventory Request

~~~json
{
  "contractVersion": 1,
  "operationId": "op-reserve-1001",
  "orderId": "ORD-1001",
  "items": [
    { "sku": "SKU-RED-001", "quantity": 2 },
    { "sku": "SKU-BLUE-002", "quantity": 1 }
  ]
}
~~~

Definition: same `operationId` with identical items is redelivery; same ID with different items is conflict. Reservation may be rejected due to out-of-stock (business), or pending/`UNKNOWN` due to DB/provider disconnection (technical). Never collapse all failures into `OUT_OF_STOCK`.

### 30.3. Sample Inventory Reply

~~~json
{
  "contractVersion": 1,
  "operationId": "op-reserve-1001",
  "outcome": "RESERVED",
  "reservationId": "res-1001",
  "expiresAt": "2026-11-21T03:20:00Z"
}
~~~

On redelivery, return the same `reservationId`/`expiresAt` from a persisted snapshot; never reserve extra stock just to construct a fresh reply. If the outcome is uncertain after a timeout, query operation state.

### 30.4. Sample Accepted Booking

~~~json
{
  "contractVersion": 1,
  "operationId": "op-book-1001",
  "outcome": "ACCEPTED",
  "statusRef": "operations/op-book-1001",
  "acceptedAt": "2026-11-21T03:00:00Z"
}
~~~

From the accepted state, emit a terminal `BOOKED` or `FAILED` event. Define late callbacks, duplicate callbacks, and tenant authorization when polling status.

### 30.5. Implementation Steps

1. Define separate request DTOs for Quote/Reserve/Book with versions and validation.
2. Define typed success/business rejection/accepted results.
3. Define stable error codes separated from technical exceptions.
4. Create authenticated caller context and verify tenant/order ownership.
5. Generate stable `requestId`/`operationId` for logical operations; persist mappings as needed.
6. Build Spring Messaging Gateway interfaces and request/reply channels.
7. Route by allowlisted operation, never arbitrary channel names.
8. Use dedicated Service Activators/Transformers per operation.
9. Have Quote return a synchronous reply with `validUntil`/`rateVersion`.
10. Have Reserve use a transactional inbox/idempotent effect; reply holds durable reservation ID.
11. Have Book return `ACCEPTED` after persisting command/outbox, emitting final result via event.
12. Configure deadlines, request/reply timeouts, transport TTLs, and retry budgets.
13. Keep correlation/`replyChannel` in proper scopes without collapsing them into business IDs.
14. Reject malformed requests, unauthorized requests, and unknown reply variants.
15. Add unit/Spring proxy/wire contract/adapter integration tests.
16. Simulate lost reply after effect commit; ensure retries do not create a second reservation.
17. Simulate callbacks arriving after deadline and redelivery with the same `eventId`.
18. Add metrics, tracing, DLQ/quarantine, and recovery runbooks.

### 30.6. Acceptance Matrix

| Scenario | Expected Outcome |
| --- | --- |
| Valid quote | `QUOTED` with amount/currency/rateVersion/validUntil |
| Unsupported `serviceLevel` | `REJECTED` or schema error per contract |
| Response `requestId` mismatch | Never deliver reply to wrong caller |
| v2 reply to v1-only client | Compatibility error |
| Same reserve `operationId` replay | One reservation, same receipt |
| Same reserve ID, different payload | `ID_CONFLICT` |
| Lost reserve reply after commit | Lookup/reconcile, never reserve twice |
| Carrier booking accepted | Command durably persisted per contract |
| Forged callback | Authorization/signature rejection |
| Duplicate callback | Never trigger business effect twice |
| Gateway reply timeout | `UNKNOWN`, never auto-convert to `REJECTED` |
| Two tenants with same `orderId` | No leaked or mixed operations |
| Async partial results | Released per manifest/deadline |
| Network converter drops `requestId` | Caught by contract test |
| DLQ replay after v2 deploy | Version-aware parser/handler |

### 30.7. Passing Criteria

A client team reading only **contract docs/schemas** must know:

- Which request to send, which fields are required, and which versions are supported.
- When `QUOTED`/`RESERVED`/`ACCEPTED`/`REJECTED` is returned.
- When state must be treated as `UNKNOWN`.
- How to use `requestId`/`operationId` across retries.
- How to correlate replies and verify identity.
- When deadlines expire and how to query durable state.
- Which errors require fixing input vs. which may be retried.
- Where access permissions and tenant scoping are enforced.

If clients must read server implementation code to guess these details to use the API safely, the request/reply contract is incomplete.

## 31. Self-Check Questions

1. In what failure modes does Remote Procedure Invocation differ from an in-JVM Java method call?
2. Why does a Java method returning `ShippingQuoteReply` still require a request/reply schema across a network?
3. What information must a request contract contain beyond business fields?
4. Why should `requestId` stay stable across retries of the same logical request?
5. Are `requestId` and `businessCorrelationKey` always the same value?
6. How does Spring `MessageHeaders.ID` differ from `businessRequestId`?
7. Can a Messaging Gateway's temporary `replyChannel` survive a restart?
8. Must `JMSCorrelationID`/AMQP `correlationId` always equal `businessRequestId`?
9. How must a reply whose `requestId` does not match the original request be handled?
10. Why does a `QUOTED` reply need currency, `rateVersion`, and `validUntil`?
11. What risks does a `double` quote amount pose to wire consumers?
12. How does `ShippingQuoteRejected` differ from `SocketTimeoutException`?
13. Should an unsupported `serviceLevel` return a typed business rejection?
14. Can a DB timeout automatically convert into `REJECTED`? Why or why not?
15. Why does `ReplyTimeout` not prove the server created no side effects?
16. With `DirectChannel`, does `replyTimeout` guarantee terminating a running handler?
17. When should you switch from sync RPC to `ACCEPTED` + completion event?
18. How far must command persistence succeed before returning HTTP `202 Accepted`?
19. Why should business deadlines be absolute `Instant`s across multiple services?
20. What should happen to a late reply after the Gateway caller timed out?
21. Why does `@Header("trustedTenantId")` not perform authentication on its own?
22. Can `requestId` be used as a secret token to query operation status?
23. When must an idempotency key include `producerId` or `operationType`?
24. Is the same `operationId` with a different payload digest a normal duplicate?
25. What bug does the crash window between writing `SEEN` and dispatch cause?
26. Which gap in side-effecting RPCs does transactional outbox/inbox solve?
27. If quote pricing rules change between retries, how do you preserve the same reply per contract?
28. May a versioned upcaster invent defaults that alter semantics?
29. How do adding an optional field and changing the meaning of `amount` differ in compatibility?
30. Why should domain DTOs and wire DTOs be separated when representing money?
31. What does a Gateway proxy integration test prove that a service unit test cannot?
32. Does a contract test checking only Jackson JSON prove `HeaderMapper` works over JMS?
33. When a Splitter creates multiple child results, does the Gateway caller pick the final reply automatically?
34. How do an Aggregator's correlation and release strategy differ in responsibility?
35. Which metrics distinguish dispatch failures from reply timeouts?
36. If a completion callback has the right `operationId` but comes from a forged producer, how do you handle it?
37. If a broker receives an ACK before the business handler commits, can the caller consider the operation completed?
38. Why should authorization failures never be retried indefinitely?
39. When `errorChannel` receives an `ErrorMessage`, is its payload automatically the domain `ShippingQuoteRequest`?
40. What signs indicate you should choose durable workflow state over a sync Gateway invocation?

## 32. Design and Operations Checklist

### 32.1. Request Contract

- Operation name and semantics clearly documented: read-only, idempotent, or side-effecting.
- Request includes an explicit version/operation discriminator.
- Required fields, types, lengths, nullability, enums, and units published.
- `requestId` or `operationId` has unique scope, issuance rules, and clear lifecycle.
- Retries of the same logical operation preserve the proper identity.
- Never share one ID across different business operations unless explicitly permitted by contract.
- Include a business deadline if the operation has a multi-hop time budget.
- Payload validation happens before business effects.
- Policy exists for unknown schemas/enums; never default to success.

### 32.2. Reply Contract

- Reply echoes the matching `requestId`/`operationId` for correlation.
- Outcomes are explicitly typed: success, business reject, accepted/pending if applicable.
- Success reply contains all promised fields: currency, amount precision, `rateVersion`, expiry.
- Business rejection has a stable error code and safe message.
- Technical exceptions/timeouts are never disguised as conclusive business rejections.
- Never accept responses with mismatched `requestId`/version or wrong tenant.
- Defined behavior for late replies, duplicate replies, and conflicting terminal outcomes.
- Schema evolution/backward compatibility and consumer-driven contract tests in place.

### 32.3. Spring Integration Topology

- `@MessagingGateway` interface registered and request channel has clear ownership.
- `@Payload`/`@Header` mappings unambiguous, header names consistent.
- Service Activator has one clear consumer on `DirectChannel` if flow expects a single handler.
- Handler returns typed reply or defines proper one-way semantics.
- Reply channel/temporary destination preserved per framework/adapter contract.
- Never confuse `businessCorrelationKey` with temporary `replyChannel` or transport correlation.
- Routers/Transformers/Subflows do not accidentally strip identity.
- If using Splitter/Aggregator, group scope and release strategy are defined.
- `requestTimeout`/`replyTimeout`/remote timeouts measured and tested per channel semantics.
- `ErrorMessage`/`errorChannel` and durable DLQ persistence clearly distinguished.
- Bounded queues, executors, rate limits, and backpressure configured when async.

### 32.4. Security and Data

- Producer/caller authenticated.
- Tenant and shipment/order permissions authorized.
- Never trust custom tenant/role/correlation headers from clients just because they mapped to Spring headers.
- Both remote requests and replies verified for source/tenant/operation binding.
- Never deserialize arbitrary Java class names from the wire.
- Never copy control headers `replyChannel`/`errorChannel` arbitrarily from external requests.
- Logs, traces, and quarantined payloads redacted and protected.
- Error messages never leak stack traces/tokens/internal SQL.
- Status/callback endpoints check operation permissions, not just knowledge of an ID.

### 32.5. Reliability and Operations

- Side-effecting commands have idempotency keys and a durable ledger.
- Ledger detects same-key/different-payload conflicts.
- Recovery exists for gaps between accepted, dispatch, and commit.
- Retries bounded, backoff/jittered, and deadline-aware.
- `UNKNOWN` state reconciled, never assumed `NOT_EXECUTED`.
- Policy exists to preserve reply snapshots/`rateVersion` for replays.
- Late replies and duplicate callbacks handled durably.
- Schema migrations cover persisted events, DLQ, and replays.
- Metrics distinguish mapping, send, business reject, remote error, and reply timeout.
- Dashboards/SLOs exist for pending operations and reconciliation backlog.
- Runbook rehearsed for lost replies after effect commit.

### 32.6. Testing

- Unit tests for request constructor and all reply variants.
- Tests for amount/currency precision, timestamps, and validity.
- Tests for business rejection vs. technical exceptions.
- Spring context test invoking real Gateway proxy and receiving typed reply.
- Tests for missing/mismatched `requestId` header and unauthorized tenant.
- Tests for reply `requestId`/version mismatch.
- Wire JSON Schema/serialization tests for v1/v2.
- Adapter contract tests for HTTP/JMS/AMQP correlation/header mapping.
- Tests for timeouts and late replies under real async topologies.
- Tests for retries/dedup, `ID_CONFLICT`, and process restarts.
- Tests for two tenants sharing entity IDs with no mixed replies.
- Tests for partial/duplicate results if using Scatter-Gather.

## 33. Summary

**Request and reply contracts** in Remote Procedure Invocation are more than a Java method signature:

~~~text
Verified caller
    |
    +-- Typed request
    |     contractVersion
    |     requestId / operationId
    |     typed business fields
    |
    v
Messaging Gateway -> Spring Integration flow -> remote adapter/service
    |                                          |
    |                                          +-- business success/reject
    |                                          +-- technical error/timeout
    v
Typed reply
    contractVersion
    matching requestId
    exactly one legal outcome
    explicit amount/currency/time/error semantics
~~~

A strong contract separates **computed**, **business-rejected**, **accepted for further processing**, and **unknown whether remote executed**. A Gateway lets applications call a clean Java API and Spring Integration can route, transform, retry, and correlate messages, yet the system still requires **stable identity, schema versioning, reply matching, authorization, timeout policies, idempotency, and recovery**.

Only when these rules are published and tested across **domain DTOs, Messaging Gateway, Service Activator, and wire adapters** can RPC-like integration scale safely across multiple services and deployment versions.

## References

- [Enterprise Integration Patterns — Integration Styles](https://www.enterpriseintegrationpatterns.com/patterns/messaging/IntegrationStylesIntro.html): integration styles including File Transfer, Shared Database, Remote Procedure Invocation, and Messaging.
- [Enterprise Integration Patterns — Request-Reply](https://www.enterpriseintegrationpatterns.com/patterns/messaging/RequestReply.html): request/reply, correlation identifiers, and reply addresses.
- [Enterprise Integration Patterns — Messaging Gateway](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingGateway.html): hiding messaging APIs behind application interfaces.
- [Enterprise Integration Patterns — Correlation Identifier](https://www.enterpriseintegrationpatterns.com/patterns/messaging/CorrelationIdentifier.html): linking replies with related requests.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): Messaging Gateway, method mappings, request/reply timeouts, and error handling.
- [Spring Integration Reference — Service Activator](https://docs.spring.io/spring-integration/reference/service-activator.html): turning Messages into POJO invocations, replies, and output channels.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): DirectChannel, ExecutorChannel, and QueueChannel.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): synchronous/asynchronous errors, ErrorMessage, and error channels.
- [Spring Integration Reference — Routers](https://docs.spring.io/spring-integration/reference/router.html): metadata-based routing and routing defaults.
- [Spring Integration Reference — Transformer](https://docs.spring.io/spring-integration/reference/transformer.html): payload conversion and header propagation.
- [Spring Integration Reference — Splitter](https://docs.spring.io/spring-integration/reference/splitter.html): child message sequence/correlation metadata.
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): grouping, release strategy, timeouts, and partial results.
- [Spring Integration Reference — HTTP Support](https://docs.spring.io/spring-integration/reference/http.html): request/reply adapters and gateways over HTTP.
- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): JMS inbound/outbound gateways, headers, and correlation.
- [Spring Integration Reference — AMQP Support](https://docs.spring.io/spring-integration/reference/amqp.html): AMQP inbound/outbound gateways and reply behavior.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): idempotency advice and duplicate detection.
- [Spring Framework — Integration testing with Spring TestContext](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html): building Spring contexts and integration tests.

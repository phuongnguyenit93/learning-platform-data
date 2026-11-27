# Passing Envelopes Through Subflows

## 1. Context: Messages Branch Out Without Losing Context

In the **Envelope wrapper** chapter of module **SPRING_INTEGRATION_PATTERN**, we learn to implement Enterprise Integration Patterns with **Spring Integration** to build loosely coupled and extensible message flows. Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation are routinely combined in a single application. When a message travels from the main flow into a **subflow**, the question is not only “did the payload reach the handler?” but also “**which context must remain intact when the message returns to the shared flow?**”

For example, a shipping-fee calculation system receives a request:

~~~json
{
  "metadata": {
    "schemaVersion": 1,
    "tenantId": "tenant-a",
    "eventId": "evt-ship-901",
    "businessCorrelationKey": "shipping:tenant-a:SHIP-901:7",
    "traceId": "trace-901",
    "sourceSystem": "ORDER_SERVICE",
    "receivedAt": "2026-11-21T03:00:00Z"
  },
  "payload": {
    "shipmentId": "SHIP-901",
    "serviceLevel": "EXPRESS",
    "packageCount": 2
  }
}
~~~

The flow can route to **standardSubflow** or **expressSubflow** to compute pricing, then converge on a shared output channel. If the handler returns only the monetary amount, stripping tenant, `eventId`, business correlation, or `traceId`, downstream components may not know which request the result belongs to. If the handler generates fresh metadata on every retry, redeliveries of the same event may be treated as separate work items.

~~~mermaid
flowchart LR
    I["Trusted ingress"] --> E["DomainEnvelope: metadata + request"]
    E --> R{"Router: service level"}
    R -->|"STANDARD"| S["standardSubflow"]
    R -->|"EXPRESS"| X["expressSubflow"]
    S --> M["DomainEnvelope: metadata + quote"]
    X --> M
    M --> V["Common validation"]
    V --> O["Business output / persistence"]
    R -.->|"UNKNOWN"| Q["Reject / quarantine"]
~~~

**Core idea:** with an envelope carrying business context, a subflow **transforms the payload per its responsibility** while retaining the metadata needed for routing, observability, reconciliation, error handling, and idempotency. That does not mean every header or every field must be copied unconditionally.

### Lesson Objectives

1. Distinguish **Envelope Wrapper (EIP)** from a **Spring Message** (payload and headers) and from HTTP/JMS/AMQP wire envelopes.
2. Design an immutable, versioned envelope carrying sufficient identity/context without embedding arbitrary infrastructure objects.
3. Pass envelopes through a Router and child **IntegrationFlows** without losing business correlation or `eventId`.
4. Understand the difference between **transforming the payload inside an envelope**, **unwrapping/re-wrapping**, and **creating a new Message**.
5. Handle context across Splitter, publish-subscribe, Scatter-Gather, Gateway, and adapters deliberately.
6. Protect metadata across validation, retries, timeouts, redeliveries, multi-tenancy, and trust boundaries.
7. Write Java DSL, unit tests, and integration tests proving invariants hold across subflows.

## 2. What Is Envelope Wrapper?

According to Enterprise Integration Patterns, **Envelope Wrapper** wraps a message inside an outer structure to carry information needed by the application or integration system, while the business content sits inside. Wrapping/unwrapping can occur when traversing an environment that requires a different representation.

~~~text
Envelope
├── metadata
│   ├── schemaVersion
│   ├── tenantId
│   ├── businessCorrelationKey
│   ├── eventId
│   └── trace context
└── payload
    ├── shipmentId
    ├── serviceLevel
    └── packageCount
~~~

Not every metadata field is mandatory for every system. A good envelope must have an **explicit contract**: which fields ingress supplies, which fields a subflow may update, which fields are serialized externally, and which are internal only.

### 2.1. Three Layers Commonly Mislabeled as “Envelope”

| Layer | Example | Scope | Who owns it? |
| --- | --- | --- | --- |
| **Domain/Application envelope** | `DomainEnvelope(metadata, payload)` | Across subflows or across the wire with an explicit schema | Application, business contract |
| **Spring Message wrapper** | Message payload + `MessageHeaders` | Inside Spring Integration runtime | Framework and endpoints |
| **Transport envelope** | HTTP headers/body, JMS properties, AMQP properties, TCP frames | Across network/broker | Protocol adapter and wire contract |

A Spring Message can hold a **`DomainEnvelope` as its payload**:

~~~text
Spring Message
  headers:
    id: generated framework message id
    replyChannel: runtime channel (if present)
    errorChannel: runtime channel (if present)
    trace/broker/sequence headers...
  payload:
    DomainEnvelope
      metadata: tenantId, eventId, correlationKey, schemaVersion...
      payload: DeliveryRequest
~~~

Thus there are **two wrapper layers**, which is not a design flaw. The outer layer is used by the framework to execute the flow; the application layer can survive serialization, durable storage, or transmission to another service.

### 2.2. Do Not Confuse Envelope Wrapper with Normalizer

| Pattern | Primary question | Example |
| --- | --- | --- |
| **Envelope Wrapper** | Which data and context must travel together? | Wrapping a quote request with `eventId`/tenant/correlation |
| **Normalizer** | Which single schema do differing schemas converge into? | ERP JSON and CSV → `CanonicalOrder` |
| **Content-Based Router** | Which branch does the message take? | `STANDARD` → `standardSubflow` |
| **Transformer** | How is the payload or Message structure transformed? | `DeliveryRequest` → `DeliveryQuote` |
| **Aggregator** | Which messages must be combined? | Multiple supplier replies → one report |

A Normalizer can convert **the payload inside** a `DomainEnvelope`. A Router can inspect payload/envelope info to pick a subflow. An Aggregator can group by `businessCorrelationKey` carried in the envelope. The patterns complement one another; **Envelope Wrapper does not replace Router/Transformer/Aggregator**.

### 2.3. Why Do Subflows Expose Risks?

A child `IntegrationFlow` might:

- Receive the message and replace the payload via a Transformer.
- Return a **complete Message**, where headers propagate differently than returning only a payload.
- Return **only the payload**, stripping the application envelope.
- Send to a Gateway/adapter, where not every header survives the wire.
- Split into multiple child messages with their own sequencing/correlation.
- Execute asynchronously with retries, reconstructing a message from persisted data.

If your design assumes “the envelope is always preserved automatically” without verifying these points, bugs may appear only on retries, when switching to `ExecutorChannel`, or when swapping connectors.

## 3. Contract for Passing Envelopes Through Subflows

Before writing Java DSL, define the invariants:

| Data | Entering a subflow | Exiting a subflow | Reason |
| --- | --- | --- | --- |
| **tenantId** | Already verified | **Unchanged** | Tenant isolation |
| **eventId** | Logical event identity | **Unchanged** if same logical event | Deduplication/redelivery |
| **businessCorrelationKey** | Workflow/group ID | **Unchanged** within same workflow | Correlation |
| **schemaVersion** | Current envelope version | Preserved or migrated **under control** | Consumer reads right schema |
| **traceId** | Observability context | Preserve trace link; `spanId` may change | Tracing |
| **sourceSystem** | Authenticated source | **Never self-declare another source** | Audit |
| **receivedAt** | Timestamp issued at ingress | **Unchanged** | Distinguish original ingress from processing time |
| **payload** | `DeliveryRequest` | Becomes `DeliveryQuote` | Transformer responsibility |
| **attemptId** | Per retry attempt | **Can change** per attempt | Operational observability |
| **replyChannel** | Runtime Spring header | Managed by framework | Not domain metadata |

Do not write a helper that “copies everything from input to output” if the input contains untrusted data. **Selective preservation by contract** differs from **blind copying**.

### 3.1. “Same Logical Event” vs. “New Derived Event” Contracts

`eventId` does not always remain unchanged:

- **Internal Transformer:** same logical event changing representation, usually keeps `eventId`.
- **Splitter producing multiple independent child events:** each child needs its own identity if deduplication/side effects are per child.
- **A new business event emitted:** may need a new `eventId` plus `parentEventId`/`causationId` to link provenance.

Example:

~~~text
Original eventId: evt-shipment-901

Routed to EXPRESS subflow to compute quote:
  eventId: evt-shipment-901      (same logical work, changed representation)

Split into 3 parcels for independent processing:
  child event IDs:
    evt-shipment-901:parcel:1
    evt-shipment-901:parcel:2
    evt-shipment-901:parcel:3
  parentEventId: evt-shipment-901
  businessCorrelationKey: shipping:tenant-a:SHIP-901:7
~~~

Never reuse the same `eventId` across three child business effects and let an inbox treat the second and third children as duplicates of the first.

### 3.2. Immutability Does Not Mean the Same Object Instance

When transforming `DomainEnvelope<DeliveryRequest>` into `DomainEnvelope<DeliveryQuote>`, the subflow creates a **new envelope object** with unchanged metadata. Unit tests should compare **metadata values**, rather than requiring input and output to share Java object identity.

When metadata is an immutable record, subflows can safely share the same metadata instance without mutation. If metadata holds a mutable `Map`/`List`, defensively copy it or use immutable collections; records are only shallowly immutable if referenced fields remain mutable.

## 4. Designing a Typed, Immutable `DomainEnvelope`

Java 17 records define a concise, clear contract:

~~~java
import java.time.Instant;
import java.util.Objects;

record EnvelopeMetadata(
        int schemaVersion,
        String tenantId,
        String eventId,
        String businessCorrelationKey,
        String traceId,
        String sourceSystem,
        Instant receivedAt) {

    EnvelopeMetadata {
        if (schemaVersion != 1) {
            throw new IllegalArgumentException("UNSUPPORTED_ENVELOPE_VERSION");
        }
        if (tenantId == null
                || !tenantId.matches("[a-z0-9_-]{1,48}")) {
            throw new IllegalArgumentException("INVALID_TENANT_ID");
        }
        if (eventId == null
                || !eventId.matches("[A-Za-z0-9_:-]{1,120}")) {
            throw new IllegalArgumentException("INVALID_EVENT_ID");
        }
        if (businessCorrelationKey == null
                || businessCorrelationKey.isBlank()
                || businessCorrelationKey.length() > 200) {
            throw new IllegalArgumentException("INVALID_CORRELATION_KEY");
        }
        if (traceId == null || traceId.isBlank()
                || traceId.length() > 128) {
            throw new IllegalArgumentException("INVALID_TRACE_ID");
        }
        if (sourceSystem == null || sourceSystem.isBlank()
                || sourceSystem.length() > 80) {
            throw new IllegalArgumentException("INVALID_SOURCE");
        }
        Objects.requireNonNull(receivedAt, "receivedAt");
    }
}

record DomainEnvelope<T>(
        EnvelopeMetadata metadata,
        T payload) {

    DomainEnvelope {
        Objects.requireNonNull(metadata, "metadata");
        Objects.requireNonNull(payload, "payload");
    }

    <R> DomainEnvelope<R> mapPayload(R nextPayload) {
        return new DomainEnvelope<>(metadata, nextPayload);
    }
}
~~~

**`mapPayload()`** is the core operation of this lesson: constructing a new envelope with the **original metadata** and a payload of a different type. It never overwrites `eventId`/`tenantId`, never alters `sourceSystem`, and never generates a new `businessCorrelationKey` on every subflow pass.

### 4.1. `DomainEnvelope` Is Not Automatically a Client-Facing DTO

A sender can craft JSON with `tenantId="tenant-admin"` and any `eventId`. Record constructors validate syntax only, **never authorization**. At ingress you must:

1. Parse wire messages according to supported `schemaVersion` and size limits.
2. Authenticate clients/producers via tokens, mTLS, or appropriate broker ACLs.
3. Look up tenant and business workflow from a trusted source.
4. **Construct `EnvelopeMetadata` internally** from verified details.
5. Only then send `DomainEnvelope` to a channel reserved for trusted envelopes.

Never wire external adapters directly into internal subflows that assume metadata is already trusted.

### 4.2. Choosing Identity Sources and Correlation Scopes

If two tenants both have `shipmentId=SHIP-901`, using `shipmentId` alone as `businessCorrelationKey` mixes groups. If the same shipment undergoes two valid processing runs, distinguish the **workflow epoch**.

~~~text
tenant-a / SHIP-901 / epoch 7:
  shipping:tenant-a:SHIP-901:7

tenant-b / SHIP-901 / epoch 7:
  shipping:tenant-b:SHIP-901:7

tenant-a / SHIP-901 / epoch 8:
  shipping:tenant-a:SHIP-901:8
~~~

Compute or look up the correlation key from verified tenant + workflow identity **once at ingress**, and preserve it across subflows. Never pick a new epoch just because a broker redelivered an old message.

## 5. Business Example: One Request, Two Pricing Methods

To separate routing from transport protocols, we use two service levels: `STANDARD` and `EXPRESS`. Each branch returns the same `DeliveryQuote` type using different pricing logic.

~~~java
import java.math.BigDecimal;
import java.util.Objects;

enum ServiceLevel {
    STANDARD,
    EXPRESS
}

record DeliveryRequest(
        String shipmentId,
        ServiceLevel serviceLevel,
        int packageCount) {

    DeliveryRequest {
        if (shipmentId == null
                || !shipmentId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("INVALID_SHIPMENT_ID");
        }
        Objects.requireNonNull(serviceLevel, "serviceLevel");
        if (packageCount < 1 || packageCount > 1_000) {
            throw new IllegalArgumentException("INVALID_PACKAGE_COUNT");
        }
    }
}

record DeliveryQuote(
        String shipmentId,
        ServiceLevel serviceLevel,
        BigDecimal amountVnd) {

    DeliveryQuote {
        Objects.requireNonNull(shipmentId, "shipmentId");
        Objects.requireNonNull(serviceLevel, "serviceLevel");
        Objects.requireNonNull(amountVnd, "amountVnd");
        if (amountVnd.signum() < 0 || amountVnd.scale() > 0) {
            throw new IllegalArgumentException("INVALID_VND_AMOUNT");
        }
    }
}
~~~

In reality, shipping fees also depend on weight, destination, surcharges, and tariff versions. The example uses **30,000 VND/package for STANDARD** and **80,000 VND/package for EXPRESS** to demonstrate envelope propagation, **not production pricing or financial rules**.

### 5.1. Branches Transform Only the Payload

~~~java
import java.math.BigDecimal;

final class DeliveryQuoteTransformer {

    DomainEnvelope<DeliveryQuote> standardQuote(
            DomainEnvelope<?> input) {
        return calculate(input, ServiceLevel.STANDARD, 30_000L);
    }

    DomainEnvelope<DeliveryQuote> expressQuote(
            DomainEnvelope<?> input) {
        return calculate(input, ServiceLevel.EXPRESS, 80_000L);
    }

    private DomainEnvelope<DeliveryQuote> calculate(
            DomainEnvelope<?> input,
            ServiceLevel expected,
            long unitPriceVnd) {

        if (!(input.payload() instanceof DeliveryRequest request)) {
            throw new IllegalArgumentException("UNEXPECTED_PAYLOAD_TYPE");
        }
        if (request.serviceLevel() != expected) {
            throw new IllegalStateException("WRONG_SUBFLOW");
        }

        BigDecimal total = BigDecimal.valueOf(unitPriceVnd)
                .multiply(BigDecimal.valueOf(request.packageCount()));

        return input.mapPayload(new DeliveryQuote(
                request.shipmentId(),
                expected,
                total));
    }
}
~~~

Three details to notice:

1. **`input.mapPayload(...)`** creates a new envelope without regenerating metadata.
2. Each subflow method re-checks `serviceLevel` to catch misrouting rather than trusting channel names blindly.
3. The logic uses typed values (**`BigDecimal`**, **enum**) and returns a **`DeliveryQuote`**, not an arbitrary `String` or `Map` downstream must guess.

### 5.2. Input and Output of Each Branch

~~~text
Input:
  DomainEnvelope<DeliveryRequest>
    metadata:
      eventId = evt-ship-901
      tenantId = tenant-a
      businessCorrelationKey = shipping:tenant-a:SHIP-901:7
    payload:
      shipmentId = SHIP-901
      serviceLevel = EXPRESS
      packageCount = 2

expressSubflow:
  verify serviceLevel == EXPRESS
  calculate quote

Output:
  DomainEnvelope<DeliveryQuote>
    metadata:
      eventId = evt-ship-901                 (preserved)
      tenantId = tenant-a                    (preserved)
      businessCorrelationKey = shipping:tenant-a:SHIP-901:7
    payload:
      shipmentId = SHIP-901
      serviceLevel = EXPRESS
      amountVnd = 160000
~~~

This is a **representation change for the same request**. If the business decides to publish a brand-new `QUOTE_CREATED` event to a broker for another service, emitting that new event can use a **new `eventId`** with `parentEventId`/`causationId`; do not equate it with this internal transformation.

## 6. Java DSL: Router Directing to Two Subflows and One Converging Channel

A testable approach is defining subflows as **`IntegrationFlow` beans with explicit input channels**, and having a Router pick the channel. Both branches send results to **`quoteOutput`**.

### 6.1. Configuring the `MessageChannel` Beans

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
class DeliveryEnvelopeFlowConfig {

    @Bean
    MessageChannel envelopeInput() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel standardRequests() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel expressRequests() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel quoteOutput() {
        return new QueueChannel();
    }

    @Bean
    QueueChannel rejectedEnvelopeMessages() {
        return new QueueChannel();
    }

    @Bean
    DeliveryQuoteTransformer deliveryQuoteTransformer() {
        return new DeliveryQuoteTransformer();
    }

    // IntegrationFlow beans are declared below.
}
~~~

This is the top portion of a single configuration class. The flow beans in the next snippets **belong inside `DeliveryEnvelopeFlowConfig`**, not as redeclarations of the same class name.

### 6.2. Router Preserves the Envelope Wrapper

~~~java
// @Bean method inside DeliveryEnvelopeFlowConfig.
@Bean
IntegrationFlow envelopeRouterFlow() {
    return IntegrationFlow.from("envelopeInput")
            .route(DomainEnvelope.class, envelope -> {
                if (!(envelope.payload()
                        instanceof DeliveryRequest request)) {
                    return "UNSUPPORTED";
                }
                return request.serviceLevel().name();
            }, mapping -> mapping
                    .channelMapping(
                            "STANDARD", "standardRequests")
                    .channelMapping(
                            "EXPRESS", "expressRequests")
                    .defaultOutputChannel("rejectedEnvelopeMessages"))
            .get();
}
~~~

**Key observation:** the Router inspects the inner payload only to select the route. **Messages sent into each branch still have `DomainEnvelope<DeliveryRequest>` as payload**; the Router does not unwrap metadata to forward `DeliveryRequest` alone.

If a request carries an unsupported payload type, the default output channel preserves the message for quarantine/auditing. Validation failures throwing exceptions or handler errors belong to the **error path** and do not route to the default output route by default.

### 6.3. Subflows Handle Specific Business Logic

~~~java
// Two @Bean methods inside DeliveryEnvelopeFlowConfig.
@Bean
IntegrationFlow standardDeliverySubflow(
        DeliveryQuoteTransformer mapper) {
    return IntegrationFlow.from("standardRequests")
            .transform(DomainEnvelope.class, mapper::standardQuote)
            .channel("quoteOutput")
            .get();
}

@Bean
IntegrationFlow expressDeliverySubflow(
        DeliveryQuoteTransformer mapper) {
    return IntegrationFlow.from("expressRequests")
            .transform(DomainEnvelope.class, mapper::expressQuote)
            .channel("quoteOutput")
            .get();
}
~~~

Transformer endpoints receive a **`DomainEnvelope`** and return a **`DomainEnvelope`**. Spring Message headers may propagate per Transformer semantics, yet **critical application metadata already resides inside the payload envelope**, avoiding reliance on whether external clients send custom HTTP/JMS headers.

**Version note:** Java DSL signatures and type inference can differ across Spring Integration releases. These snippets depict DSL APIs for modern versions; when integrating into a real project, verify package imports and run tests against your project's dependencies. Building/academic QA is outside the scope of this authoring step.

### 6.4. Forwarding Downstream

From `quoteOutput`, a consumer can:

1. Read `EnvelopeMetadata` to identify tenant/workflow and `eventId`.
2. Verify the payload is **`DeliveryQuote`** and validate `amountVnd` invariants.
3. Persist results or invoke a service using a **business idempotency key**.
4. Emit traces/audits and update workflow state as needed.

Never unwrap the envelope right before sending to a downstream consumer that needs correlation; if downstream expects `DeliveryQuote` alone, include an **intentional conversion step** that persists or forwards sufficient context by another mechanism.

## 7. Inline `subFlowMapping`: Same Semantics, Shorter Form

Spring Integration Java DSL also supports defining **nested subflows right inside the Router**, instead of mapping only to channel names:

~~~java
// Illustrative variant: replaces envelopeRouterFlow and the two
// separate subflow beans in Section 6; DO NOT register both simultaneously.
@Bean
IntegrationFlow inlineEnvelopeRouting(
        DeliveryQuoteTransformer mapper) {
    return IntegrationFlow.from("envelopeInput")
            .route(DomainEnvelope.class, envelope -> {
                if (!(envelope.payload()
                        instanceof DeliveryRequest request)) {
                    return "UNSUPPORTED";
                }
                return request.serviceLevel().name();
            }, routes -> routes
                    .subFlowMapping("STANDARD", sub -> sub
                            .transform(
                                    DomainEnvelope.class,
                                    mapper::standardQuote)
                            .channel("quoteOutput"))
                    .subFlowMapping("EXPRESS", sub -> sub
                            .transform(
                                    DomainEnvelope.class,
                                    mapper::expressQuote)
                            .channel("quoteOutput"))
                    .defaultOutputChannel("rejectedEnvelopeMessages"))
            .get();
}
~~~

**Do not register both** the Section 7 variant and the Section 6 Router/Subflows on **the same `envelopeInput`**: two Router consumers on a `DirectChannel` cause unintended dispatch behavior. Pick **one** wiring style.

In the inline variant, each subflow lambda is a separate processing flow chosen by the Router. The envelope contract is **unchanged**: same metadata, only the payload becomes `DeliveryQuote`.

### 7.1. When to Choose `subFlowMapping` Over Named Channels?

| Option | Best suited for | Watch out for |
| --- | --- | --- |
| **Named channels + separate `IntegrationFlow` beans** | Large branches, independent metrics/tests, module ownership | More beans, yet clearer boundaries |
| **Inline `subFlowMapping`** | Short branches, routing logic easy to read in one place | Avoid overly long lambdas or mixing responsibilities |
| **Single `Transform` with switch** | Very few cases, pure simple logic | Easily grows into a huge `if`/`else` block as sources expand |

Whichever option you pick, define error paths, timeouts, output channels, correlation, and idempotency.

### 7.2. Routers Have Differing Reply Semantics

A Router dispatches a Message to a channel; a subflow might end at a Service Activator returning no reply, or bridge to another channel. Do not assume that merely because a Router picked a branch, a **Gateway caller** always receives a reply: there must be a valid reply path (and send/reply timeout contract) across all endpoints.

In particular, if a subflow returns `null` or a Filter discards the message, request/reply can end without output. When a Gateway is waiting, that leads to a reply timeout.

## 8. Three Transform Approaches and Where Envelopes Get Lost

Consider three common implementation patterns.

### 8.1. Right: Receive Envelope, Return Envelope

~~~java
DomainEnvelope<DeliveryQuote> transform(
        DomainEnvelope<DeliveryRequest> incoming) {
    DeliveryRequest request = incoming.payload();
    DeliveryQuote quote = new DeliveryQuote(
            request.shipmentId(),
            request.serviceLevel(),
            java.math.BigDecimal.valueOf(60_000L));
    return incoming.mapPayload(quote);
}
~~~

Here metadata always travels with the output. Changing the payload requires neither cloning all Spring `MessageHeaders` nor rebuilding trusted fields from raw input.

### 8.2. Wrong If Downstream Still Needs the Envelope: Return Only Processed Content

~~~java
// Returns plain payload, losing the application-level DomainEnvelope.
DeliveryQuote transform(DomainEnvelope<DeliveryRequest> incoming) {
    DeliveryRequest request = incoming.payload();
    return new DeliveryQuote(
            request.shipmentId(),
            request.serviceLevel(),
            java.math.BigDecimal.valueOf(60_000L));
}
~~~

Spring Integration may keep propagating **some Spring Message headers**, yet the output payload is no longer a `DomainEnvelope`. If downstream looks for **metadata inside the payload envelope** to serialize onto a broker, it is gone.

This is only valid when you **intentionally unwrap** at a boundary and have another mechanism retaining required context. Never treat remaining Spring Message headers as proof the domain envelope survived.

### 8.3. Wrong: Mint Random Metadata in Every Subflow

~~~java
// Anti-example: do not do this.
EnvelopeMetadata changed = new EnvelopeMetadata(
        1,
        incoming.metadata().tenantId(),
        java.util.UUID.randomUUID().toString(),
        java.util.UUID.randomUUID().toString(),
        "new-trace-every-hop",
        "UNKNOWN",
        java.time.Instant.now());

return new DomainEnvelope<>(changed, newQuote);
~~~

`eventId`, `businessCorrelationKey`, `traceId`, `sourceSystem`, and `receivedAt` were altered without a business decision. When the same event retries, this creates new groups or defeats deduplication.

**Rule:** if it is the same logical work, preserve immutable metadata. If you must record hop/subflow info, use a **separate processing context** or add an enrichment/versioned metadata structure with clear ownership.

## 9. When a Subflow Needs to Add Metadata

Sometimes a subflow must record a **verification outcome**, **pricing rule version**, or **completion timestamp**. Do not mutate a shared `Map` inside an envelope held by other subflows.

### 9.1. Separate Original Event Metadata from Derived Metadata

One option is placing derived business data inside the payload:

~~~java
// Extended DTO variant; do not declare alongside
// the minimal DeliveryQuote in Section 5.
record DetailedDeliveryQuote(
        String shipmentId,
        ServiceLevel serviceLevel,
        java.math.BigDecimal amountVnd,
        String tariffVersion,
        java.time.Instant calculatedAt) {
}
~~~

Original event metadata stays untouched while the result payload carries full details of the new decision. While Section 5 uses a minimal `DeliveryQuote`, you can adopt an **extended result type** like this when the contract requires it.

Another option is creating:

~~~java
record ProcessingContext(
        String attemptId,
        String currentStage,
        java.time.Instant processedAt) {
}
~~~

`ProcessingContext` can live in **internal** Spring Message headers to observe a single execution attempt without serializing it on every domain event. If durability across retries/restarts is needed, persist processing state keyed by event/operation ID instead of relying solely on in-memory headers.

### 9.2. Enriching the Envelope with Explicit Versioning

If integration requirements force adding a field to the **wire envelope**, evolve the schema under control:

~~~text
DomainEnvelope v1:
  schemaVersion, tenantId, eventId, correlationKey, payload

DomainEnvelope v2:
  schemaVersion, tenantId, eventId, correlationKey,
  causationId, payload
~~~

Provide v1/v2 converters, backward compatibility, tests, and a rollout plan. Never abruptly add a required field to every partner's JSON just because one new subflow wants metadata.

## 10. Spring `MessageHeaders` vs. `DomainEnvelope.metadata`

Even when `DomainEnvelope` is immutable, Spring Integration still wraps it in a Spring Message carrying framework **headers**. Keep a clean distinction:

| Attribute | Where should it live? | Reason |
| --- | --- | --- |
| **Logical `eventId`** | `DomainEnvelope.metadata` | Survives serialization, storage, and replay |
| **Verified `tenantId`** | `DomainEnvelope.metadata`, optionally mirrored in internal header | Business and security boundary |
| **`businessCorrelationKey`** | `DomainEnvelope.metadata`, mirrored to correlation header when needed | Aggregator/recovery |
| **`traceId` / trace context** | Observability context + envelope when contract requires | Cross-service linking |
| **`replyChannel`** | Spring `MessageHeaders` managed by framework | Runtime request/reply |
| **`errorChannel`** | Spring `MessageHeaders` per error handling | Runtime error routing |
| **`sequenceNumber` / `sequenceSize`** | Spring headers from Splitter/Resequencer | Subgroup and sequence position |
| **`deliveryAttempt` / retry count** | Runtime processing header or state | Can vary per attempt |
| **HTTP/JMS/AMQP properties** | Transport adapter/header mapper | Protocol scope |

### 10.1. Creating a Spring Message with Envelope-Compatible Headers

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class EnvelopeMessageFactory {

    static <T> Message<DomainEnvelope<T>> trusted(
            DomainEnvelope<T> envelope) {

        EnvelopeMetadata md = envelope.metadata();
        return MessageBuilder.withPayload(envelope)
                .setHeader("trustedTenantId", md.tenantId())
                .setHeader("businessEventId", md.eventId())
                .setHeader(
                        "businessCorrelationKey",
                        md.businessCorrelationKey())
                .setHeader(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        md.businessCorrelationKey())
                .build();
    }
}
~~~

This factory accepts a **`DomainEnvelope` already verified at ingress**. It **never** copies all HTTP/JMS headers or raw client `correlationId` values, preventing untrusted sources from hijacking `ReplyChannel`/`ErrorChannel` or forging groups.

### 10.2. Mirrored Headers Need Conflict Checks

Suppose a Message header `businessCorrelationKey` says **order-A**, while payload envelope metadata says **order-B**. Never let downstream code pick one at random:

~~~text
Spring header:  businessCorrelationKey=shipping:tenant-a:SHIP-901:7
Envelope meta:  businessCorrelationKey=shipping:tenant-b:SHIP-999:1
~~~

A boundary validator must compare them and **fail closed** on mismatch. Designate a **source of truth** (such as a registry or verified ingress envelope) and derive internal Spring headers from it. Never let a downstream Router use header A while an Aggregator uses envelope B.

### 10.3. Transformer Returning Payload vs. Transformer Returning `Message`

A Spring Integration Transformer can accept a Message and return a **payload** or return a **new `Message`**:

~~~java
// Transforms payload; framework can preserve inbound headers
// per transformer endpoint rules.
.transform(DomainEnvelope.class, mapper::expressQuote)
~~~

~~~java
// Handler manually builds a new Message. Must decide which
// runtime headers must be preserved or set.
Message<DomainEnvelope<DeliveryQuote>> wrapExplicitly(
        Message<DomainEnvelope<DeliveryRequest>> incoming) {
    DomainEnvelope<DeliveryQuote> payload =
            quoteTransformer.expressQuote(incoming.getPayload());
    return MessageBuilder.withPayload(payload)
            .setHeader("businessCorrelationKey",
                    payload.metadata().businessCorrelationKey())
            .build();
}
~~~

The second pattern **does not preserve all Spring headers**; depending on topology it can drop `replyChannel`, `errorChannel`, trace, or sequence metadata. Whenever a handler genuinely must return a `Message`, determine which headers to propagate using your **exact framework version's semantics**, while avoiding copying arbitrary untrusted source headers.

### 10.4. Do Not Substitute Spring Message ID for `eventId`

`MessageHeaders.ID` identifies a single Spring Message and can change whenever a new Message is built or crosses an adapter. `DomainEnvelope.metadata.eventId` represents the **logical event** and must stay stable across redeliveries.

~~~text
attempt 1:
  Spring Message ID = msg-a
  Domain event ID   = evt-ship-901

attempt 2:
  Spring Message ID = msg-b
  Domain event ID   = evt-ship-901
~~~

Using Spring `MessageHeaders.ID` as a deduplication key lets redeliveries slip past duplicate detection.

## 11. Where to Intentionally Unwrap the Envelope

Some business libraries only want **`DeliveryQuote`**, not `DomainEnvelope`. You can place an **adapter at the application boundary**:

~~~java
final class DeliveryQuoteHandler {
    void process(
            DeliveryQuote quote,
            EnvelopeMetadata metadata) {
        // Use metadata to enforce tenant/idempotency/correlation.
        // The domain service can receive plain quote past the boundary.
    }
}
~~~

~~~text
Before boundary:
  DomainEnvelope<DeliveryQuote>

Adapter:
  validate metadata and payload
  select business idempotency key
  call domain service(quote, verified business context)

After boundary:
  domain service needs no Spring Integration awareness
~~~

**Do not unwrap too early:** if you strip metadata before calling the business handler and later need tenant/correlation, the handler might read a `ThreadLocal`/`RequestContext` that is no longer valid once the flow uses `ExecutorChannel` or a broker.

### 11.1. Controlled Unwrapping Example

~~~java
// Method fragment at adapter invoking business service.
void handle(DomainEnvelope<?> envelope) {
    if (!(envelope.payload() instanceof DeliveryQuote quote)) {
        throw new IllegalArgumentException("EXPECTED_DELIVERY_QUOTE");
    }
    EnvelopeMetadata context = envelope.metadata();

    // Caller can enforce tenant/operation identity here.
    deliveryQuoteService.save(
            context.tenantId(),
            context.eventId(),
            context.businessCorrelationKey(),
            quote);
}
~~~

**`deliveryQuoteService`** is a placeholder service for architectural illustration; production code must add appropriate transactions, unique constraints, and idempotency. Reading context from the envelope **does not prove** the tenant was verified if an external adapter bypassed ingress validation.

### 11.2. Avoid Pointless Double-Wrapping

~~~text
DomainEnvelope<DomainEnvelope<DeliveryRequest>>
~~~

Nested wrappers sometimes make sense (such as transport wire envelope vs. domain envelope), yet if every subflow wraps another `DomainEnvelope` with the same semantics, consumers cannot tell which layer holds tenant/`eventId`. Once you have **one canonical envelope**, use **`mapPayload`** to keep a single metadata layer rather than adding identical wrappers.

## 12. Splitter: Parent Message Envelope vs. Child Message Envelopes

When a `DeliveryRequest` has three packages to process in parallel, a Splitter can create three child messages. **This is a new identity boundary**, not merely a `mapPayload` of the same event.

~~~mermaid
flowchart TB
    P["DomainEnvelope<DeliveryRequest>"] --> S["Splitter"]
    S --> A["Child envelope parcel 1"]
    S --> B["Child envelope parcel 2"]
    S --> C["Child envelope parcel 3"]
    A --> N["Child processing"]
    B --> N
    C --> N
    N --> G["Aggregator: complete parcel set"]
    G --> O["Shipment summary"]
~~~

If all three child envelopes keep **the parent's `eventId`** while downstream enforces a unique inbox on `tenant + eventId`, children 2 and 3 are blocked as duplicates. Therefore:

- **The parent workflow's `businessCorrelationKey`** can be preserved.
- **Child `eventId`** must be stable and distinct when each child is an independent unit of logical work.
- **`parentEventId`/`causationId`** must remain for provenance.
- **`sequenceNumber`/`sequenceSize`** can be attached by Spring's Splitter so child messages group properly.

### 12.1. DTO and Child Identity Rules

~~~java
record ParcelTask(
        String parentEventId,
        String shipmentId,
        int parcelNumber,
        int totalParcels) {
}

final class ParcelEnvelopes {
    private ParcelEnvelopes() {}

    static DomainEnvelope<ParcelTask> child(
            DomainEnvelope<DeliveryRequest> parent,
            int number) {
        DeliveryRequest request = parent.payload();
        if (number < 1 || number > request.packageCount()) {
            throw new IllegalArgumentException("INVALID_PARCEL_NUMBER");
        }

        EnvelopeMetadata root = parent.metadata();
        String childId = root.eventId() + ":parcel:" + number;

        EnvelopeMetadata childMeta = new EnvelopeMetadata(
                root.schemaVersion(),
                root.tenantId(),
                childId,
                root.businessCorrelationKey(),
                root.traceId(),
                root.sourceSystem(),
                root.receivedAt());

        return new DomainEnvelope<>(
                childMeta,
                new ParcelTask(
                        root.eventId(),
                        request.shipmentId(),
                        number,
                        request.packageCount()));
    }
}
~~~

Child IDs in this example combine **parent event ID + parcel number**. On retries of the same logical parent and manifest, child IDs stay stable. If package ordering can change across attempts, an index might not represent the same parcel; in real systems use a **stable `parcelId`** from the manifest. Also, `EnvelopeMetadata` validation caps `eventId` at 120 characters; production must ensure concatenated `childId` values stay within bounds or use a defined mapping/encoding.

### 12.2. Splitter Technical Correlation Can Differ from Business Key

Spring Integration's Splitter sets **`CORRELATION_ID`, `SEQUENCE_NUMBER`, and `SEQUENCE_SIZE`** headers to group child messages. That technical correlation value need not match the root workflow's **`businessCorrelationKey`**.

~~~text
DomainEnvelope.metadata.businessCorrelationKey:
    shipping:tenant-a:SHIP-901:7   (parent workflow)

Spring MessageHeaders.CORRELATION_ID:
    splitter-batch-42               (child message group)

Spring MessageHeaders.SEQUENCE_NUMBER:
    1, 2, 3
~~~

**Do not force nested Splitters to share one global `CORRELATION_ID`.** An Aggregator collecting parcel results can use the Splitter's technical group, while a higher-level Aggregator collecting business events uses the broader `businessCorrelationKey`. Clarify scope before choosing a `correlationStrategy`.

### 12.3. Using Splitter with Envelopes

~~~java
// Concept of a transport-independent splitter function.
static java.util.List<DomainEnvelope<ParcelTask>> split(
        DomainEnvelope<DeliveryRequest> parent) {

    java.util.List<DomainEnvelope<ParcelTask>> result =
            new java.util.ArrayList<>();
    for (int i = 1; i <= parent.payload().packageCount(); i++) {
        result.add(ParcelEnvelopes.child(parent, i));
    }
    return java.util.List.copyOf(result);
}
~~~

When wiring into a Spring Integration Splitter, test that sequence headers match your exact configuration/version, and verify the Aggregator releases only after receiving **distinct logical child results**, not merely after some attempts containing duplicates.

## 13. Publish-Subscribe and Recipient List: Multiple Subflows Reading One Envelope

A publish-subscribe channel can broadcast **references to the same immutable envelope** so multiple subscribers process one message—for instance, one branch writes audit logs, one computes quotes, and one records metrics.

~~~mermaid
flowchart LR
    E["DomainEnvelope<Request>"] --> P["Publish-Subscribe"]
    P --> A["Audit subflow"]
    P --> Q["Quote subflow"]
    P --> M["Metrics subflow"]
    Q --> O["Envelope<Quote>"]
~~~

### 13.1. Safe Only When Payload and Metadata Are Truly Immutable

`DomainEnvelope` is an immutable record, yet inspect the **payload** too. If the payload contains a mutable `List`, mutable `Map`, or object with setters, two subflows can still mutate data while another branch reads it.

Bad example:

~~~java
record UnsafePayload(java.util.Map<String, Object> fields) {}

// subflow A:
envelope.payload().fields().put("status", "CHANGED");

// subflow B reads the same object and sees mutated data.
~~~

Mitigations:

- Payloads use immutable records, enums, and immutable collections.
- Constructors defensively copy `Map`/`List` via **`Map.copyOf`** and **`List.copyOf`** where appropriate.
- Each subflow builds new outputs using `mapPayload` or new DTOs.
- For side effects, use idempotency and transactions; **immutable objects do not make DB writes run once**.

### 13.2. Do Not Treat Publish-Subscribe as Request with a Single Reply

When a publish-subscribe channel delivers to multiple subscribers, each subscriber can succeed or fail independently. If you need results from all three, use **Scatter-Gather/Aggregator** with explicit release/timeout policies instead of publishing and waiting for an arbitrary reply.

A Recipient List can also send messages to multiple destinations. If two recipients both write to a DB, distinguish **each recipient's `operationId`** so side effects of the two branches are not mistaken for duplicates.

### 13.3. Envelopes of Derived Results

If one root request produces three outcomes:

~~~text
root eventId = evt-ship-901

AUDIT_RECORDED  -> evt-ship-901:audit
PRICE_COMPUTED  -> evt-ship-901:price
CHECK_COMPLETED -> evt-ship-901:check
~~~

You can keep the shared `businessCorrelationKey` while assigning distinct identities to **new events** using deterministic rules or persisted mappings. If a branch merely reads the envelope and updates **metrics**, there is no need to emit a new business event.

## 14. Scatter-Gather: Combining Results Across Multiple Subflows

In Scatter-Gather, one request fans out to multiple branches and replies are combined by an Aggregator. The envelope gives every branch reply the business context proving it belongs to the same workflow.

~~~text
Request:
  eventId = quote-request-100
  businessCorrelationKey = shipping:tenant-a:SHIP-901:7

Scatter:
  rateProvider A
  rateProvider B
  rateProvider C

Gather:
  Reply A: QuoteResult, correlationKey=...
  Reply B: QuoteResult, correlationKey=...
  Reply C: QuoteResult, correlationKey=...

Aggregate:
  verify same tenant, same business key, distinct providers
  release once all terminal outcomes arrive per manifest
~~~

### 14.1. Correlation and Release Are Two Different Questions

- **CorrelationStrategy:** do the results from the three providers belong to the same logical request?
- **ReleaseStrategy:** have enough required results arrived to reach a decision?

Do not rely solely on **`group.size() == 3`** if a broker can redeliver Provider A three times. Deduplicate by provider operation/`eventId`, check expected providers, enforce timeouts, and handle terminal outcomes like `ACCEPTED`/`REJECTED`/`UNAVAILABLE`.

### 14.2. Do Not Share One Correlation Key Across Subgroups

If a batch holds multiple shipments and each shipment queries three providers, using `batchId` alone mixes all provider replies. Scopes can look like:

~~~text
batchId: B-2026-11

shipment A provider group:
  provider-quote:tenant-a:B-2026-11:SHIP-A:epoch-1

shipment B provider group:
  provider-quote:tenant-a:B-2026-11:SHIP-B:epoch-1
~~~

Only after per-shipment summaries exist does a parent Aggregator combine summaries by batch key. Envelopes can carry separate **`parentBusinessKey`** and **`currentGroupKey`** when the topology requires it.

### 14.3. Do Not Trust a Reply Merely Because Its Correlation Key Matches

Any actor knowing a group key could try injecting a fake “cheap quote” into the Aggregator. The inbound adapter must authenticate the producer, verify `providerId` and permissions for the tenant/workflow, and only then build the internal verified envelope. **Correlation is not authorization.**

## 15. Gateway and Temporary `replyChannel`

A Spring Integration **Messaging Gateway** lets Java code invoke an `IntegrationFlow` like a method. When the method awaits a reply, the framework normally uses a **temporary `replyChannel`** to route the result back to that exact invocation.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as Messaging Gateway
    participant R as Router
    participant S as Subflow
    C->>G: calculateQuote(envelope)
    G->>R: Message(payload=DomainEnvelope, replyChannel=temporary)
    R->>S: Route message
    S-->>G: DomainEnvelope<DeliveryQuote> via reply path
    G-->>C: Result payload
~~~

**`businessCorrelationKey` in `DomainEnvelope` is not the Gateway's `replyChannel`.** The same workflow may undergo multiple Gateway attempts, and each invocation must distinguish its own reply destination.

### 15.1. Illustrative Gateway Interface

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway
interface DeliveryQuoteGateway {

    @Gateway(
            requestChannel = "gatewayQuoteInput",
            replyTimeout = 5_000)
    DomainEnvelope<DeliveryQuote> calculate(
            DomainEnvelope<DeliveryRequest> request);
}
~~~

This example shows the **Gateway contract**; running it requires a flow wiring **`gatewayQuoteInput`** to a route/subflow capable of returning a reply on the right reply path. **Do not** send the reply to a separate output `QueueChannel` and expect the Gateway to find it automatically unless a compatible bridge/reply channel wiring exists.

### 15.2. Entering a Subflow and Dropping `replyChannel`

If a Transformer manually constructs a new Message containing only **`businessCorrelationKey`**, a waiting Gateway will not receive its reply. Conversely, stuffing a **temporary `replyChannel` object** into `DomainEnvelope` to send over a broker is also wrong because runtime objects are neither portable nor long-lived.

The solution separates two layers:

1. **Business context** durable inside the envelope.
2. **Gateway request/reply context** managed by the framework/adapter within the active request lifecycle.

### 15.3. When a Request Takes Minutes

A synchronous Gateway with a temporary `replyChannel` is not a workflow store. If a remote service returns HTTP 202 Accepted and sends a callback a minute later, the original Gateway call may already have returned or timed out. The callback must **correlate via business key** into persistent workflow state, never to an expired temporary channel.

When awaiting multiple results to update state, use async commands + event callbacks + an Aggregator/workflow coordinator. The API can return a `trackingId` for polling instead of holding HTTP threads indefinitely.

## 16. Over HTTP, JMS, AMQP, and TCP: Application Envelopes Need a Wire Contract

A subflow can end at an outbound gateway/adapter instead of an internal `MessageChannel`. At that point **`DomainEnvelope` is serialized to bytes**; Spring `MessageHeaders` are translated by each transport's **`HeaderMapper`/`MessageConverter`**, with no guarantee that every runtime header crosses the network.

### 16.1. Illustrative Wire Format

~~~json
{
  "schemaVersion": 1,
  "metadata": {
    "tenantId": "tenant-a",
    "eventId": "evt-ship-901",
    "businessCorrelationKey": "shipping:tenant-a:SHIP-901:7",
    "traceId": "trace-901",
    "sourceSystem": "ORDER_SERVICE",
    "receivedAt": "2026-11-21T03:00:00Z"
  },
  "payloadType": "DELIVERY_REQUEST",
  "payload": {
    "shipmentId": "SHIP-901",
    "serviceLevel": "EXPRESS",
    "packageCount": 2
  }
}
~~~

This is an **illustrative application wire contract**, not Spring Integration's default JSON format. `payloadType` or `schemaVersion` lets the parser choose the right DTO; never deserialize arbitrary client-supplied class names, which introduces polymorphic deserialization risks.

### 16.2. Transport Constraints Table

| Transport | What the protocol carries | What must be configured |
| --- | --- | --- |
| **HTTP** | Body + HTTP headers | JSON serializer, content type, header allowlist, timeout |
| **JMS** | Body + JMS headers/properties | Converter, `HeaderMapper`, `JMSReplyTo`/`JMSCorrelationID` for RPC |
| **AMQP** | Body + AMQP properties/headers | Converter, `replyTo`/correlation for RPC, broker permissions |
| **TCP** | Bytes via framing/serializer | Framing, `MessageMapper`, selected headers or DTO envelope |
| **File/SFTP** | File content + name/path/external metadata | File schema, identity, idempotency, and parsing |

Spring Message header **`replyChannel`** can hold an in-JVM `MessageChannel` object; it is not portable JSON/JMS property data. Never serialize a whole Spring Message and assume another service can restore live channel references.

### 16.3. When an Adapter Sends Only the Inner Payload

Anti-example:

~~~text
Before outbound adapter:
  Message.payload = DomainEnvelope<DeliveryRequest>

Custom converter:
  encode(message.payload.payload)      // Takes only DeliveryRequest

After remote inbound:
  Message.payload = DeliveryRequest
  DomainEnvelope metadata is lost
~~~

This is not a Router bug in the subflow; it is a **`wire converter` decision**. Write round-trip tests for encoders/decoders including metadata, not just local `IntegrationFlow` tests.

## 17. Protecting the Trust Boundary When Envelopes Return from Outside

An external producer can send JSON containing `tenantId`, `eventId`, and `businessCorrelationKey`. **Valid schema does not mean authorized.** At the inbound adapter, use connection/producer identity to establish the real tenant and source.

### 17.1. Raw Wire Record vs. Verified `DomainEnvelope`

~~~java
record DeliveryWireRequest(
        int schemaVersion,
        String claimedTenantId,
        String eventId,
        String claimedCorrelationKey,
        String traceId,
        String claimedSourceSystem,
        String receivedAtIso,
        String shipmentId,
        String serviceLevel,
        int packageCount,
        int workflowEpoch) {
}

record VerifiedProducer(
        String principalId,
        String tenantId,
        String sourceSystem) {
}

interface ShipmentWorkflowRegistry {
    boolean maySubmit(
            VerifiedProducer producer,
            String shipmentId,
            int epoch);
}
~~~

In this example, `claimedTenantId` and `claimedCorrelationKey` are **untrusted claims**. The registry must verify the shipment belongs to the verified tenant and the producer is allowed to submit that request type. Never equate string-matching `tenantId` with authentication.

### 17.2. Verifier Rebuilds an Envelope from a Trusted Source

~~~java
import java.time.Instant;

final class DeliveryEnvelopeIngress {
    private final ShipmentWorkflowRegistry registry;

    DeliveryEnvelopeIngress(ShipmentWorkflowRegistry registry) {
        this.registry = registry;
    }

    DomainEnvelope<DeliveryRequest> verify(
            DeliveryWireRequest wire,
            VerifiedProducer producer) {

        if (wire == null || producer == null
                || wire.schemaVersion() != 1) {
            throw new IllegalArgumentException("INVALID_WIRE_VERSION");
        }

        DeliveryRequest request = new DeliveryRequest(
                wire.shipmentId(),
                ServiceLevel.valueOf(wire.serviceLevel()),
                wire.packageCount());

        if (!registry.maySubmit(
                producer, request.shipmentId(), wire.workflowEpoch())) {
            throw new SecurityException("SHIPMENT_ACCESS_DENIED");
        }

        String expectedKey = "shipping:"
                + producer.tenantId()
                + ":" + request.shipmentId()
                + ":" + wire.workflowEpoch();

        if (!producer.tenantId().equals(wire.claimedTenantId())
                || !producer.sourceSystem()
                        .equals(wire.claimedSourceSystem())
                || !expectedKey.equals(wire.claimedCorrelationKey())) {
            throw new SecurityException("ENVELOPE_IDENTITY_MISMATCH");
        }

        EnvelopeMetadata trusted = new EnvelopeMetadata(
                1,
                producer.tenantId(),
                wire.eventId(),
                expectedKey,
                wire.traceId(),
                producer.sourceSystem(),
                Instant.parse(wire.receivedAtIso()));

        return new DomainEnvelope<>(trusted, request);
    }
}
~~~

**Example limitations:** production also requires size/charset limits, hardened schema parsing, checking `eventId` scope/permissions, validating remote `traceId` values, timestamp skew checks, replay protection, and source-system mappings. **`Instant.parse`** can throw `DateTimeParseException` on invalid formats; map it to an error code/HTTP response or DLQ/quarantine per contract. **`ServiceLevel.valueOf`** must also be caught and classified as an unknown enum rather than leaking raw internal exceptions to clients.

In systems using opaque workflow IDs, look up `expectedKey` from the registry rather than concatenating strings. Never use `claimedCorrelationKey` itself for authorization lookups if that could cause cross-tenant access.

### 17.3. Header Mapping Is Not Authorization

An HTTP/JMS/AMQP `HeaderMapper` can map `X-Correlation-ID` to Spring's `correlationId` header. That is merely **moving data**, not verifying its value. Verify source and workflow before using headers as Router/Aggregator keys or routing to sensitive destinations.

If an adapter is labeled trusted, draw a crisp boundary: did that adapter authenticate the source or only parse bytes? Never name a bean `trusted` and skip verification.

## 18. Async Subflows: Envelopes Do Not Rely on `ThreadLocal`

If `DirectChannel` is replaced with `ExecutorChannel`, subflows run on different threads; over a broker or restart, they leave the JVM altogether. Information stored solely in **`ThreadLocal`**, MDC, or request-scoped beans may be absent when the handler runs.

~~~text
HTTP thread:
  tenantContext = tenant-a
  send message to ExecutorChannel

Worker thread:
  tenantContext = null / stale

Correct:
  DomainEnvelope.metadata.tenantId = tenant-a
  verified business context is read from the envelope
~~~

Tracing instrumentation can actively propagate trace context across executors or brokers, yet **business identity** still must be explicitly carried in payload/envelope or persisted workflow state. MDC aids logging; it is neither an authorization mechanism nor a reliable source of business correlation.

### 18.1. Do Not Assume Output Order Matches Input Order

~~~text
Arrivals:
  Envelope #1 STANDARD
  Envelope #2 EXPRESS
  Envelope #3 STANDARD

Async completion:
  #2, #3, #1
~~~

Subflows may finish out of arrival order. If downstream requires business ordering, use sequence numbers/versions and a Resequencer or stream-key coordinator. Never sort solely by **`Instant receivedAt`** when multiple producers have unsynchronized clocks.

### 18.2. Backpressure

An envelope with a large payload fanned out to many subflows can spike memory usage. Under high traffic:

- Enforce payload size and concurrent message limits.
- Use bounded executors, queue capacities, and rejection policies.
- Set per-tenant/source quotas; monitor queue age, retries, and DLQs.
- For very large payloads, store objects durably and pass an **access-controlled storage reference**, never fetching arbitrary client-supplied URLs server-side.
- If multiple subflows share mutable bytes/collections, use immutable copies or controlled ownership.

Unbounded `QueueChannel` instances in the example simplify testing; never use unbounded queues as a backpressure “solution” in production.

## 19. Envelopes Across Retries and Redeliveries

Retries usually create a **new delivery attempt**, not a new business event. Preserve:

~~~text
logical eventId: evt-ship-901
business key: shipping:tenant-a:SHIP-901:7

attempt 1:
  transportAttemptId: attempt-a
  DomainEnvelope.metadata.eventId: evt-ship-901

attempt 2:
  transportAttemptId: attempt-b
  DomainEnvelope.metadata.eventId: evt-ship-901
~~~

If each retry mints a new `eventId` in the envelope, an inbox deduplicating by `eventId` treats the redelivery as a different event. Conversely, if an operation emits a **new derived business event**, give it its own `eventId`/`causationId` instead of forcing the source `eventId` onto every output.

### 19.1. Idempotency at Downstream, Not Just at the Router

A Router can route both redeliveries into the same subflow; that does not mean business side effects execute only once. When the quote handler writes to a database, use stable operation identity and durable state:

~~~sql
CREATE TABLE delivery_quote_effect (
    tenant_id VARCHAR(48) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    operation_name VARCHAR(80) NOT NULL,
    state VARCHAR(24) NOT NULL,
    processed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, event_id, operation_name)
);
~~~

Assuming `eventId` is stable and unique per tenant, this table protects the **`persist-delivery-quote`** effect with a primary key constraint. If `eventId` is only unique per producer, include `sourceSystem`/`producerId` in the primary key per contract.

### 19.2. Transaction Gaps

Anti-example:

~~~text
mark eventId as SEEN in DB
crash before sending envelope to next subflow
broker redelivers eventId
dedup sees SEEN and discards
=> downstream never receives it
~~~

A durable design uses an inbox/outbox transaction, or `RECEIVED -> DISPATCH_PENDING -> EFFECT_COMMITTED` states with a recovery scanner. Never discard duplicates if the original state did not finish.

### 19.3. Retries Keep Original Metadata While Updating Processing Context

Original `receivedAt` is the first ingress timestamp. A retry may have a new **`attemptStartedAt`**, **`attemptId`**, and **`retryCount`**. Keep those in tracing/runtime metadata or an appropriate processing-state record; never overwrite the original `receivedAt` and pretend the message was created later.

### 19.4. External Side Effects and `UNKNOWN`

If a subflow calls a payment/shipping provider and times out, the provider may have executed the effect despite no response arriving. Never treat a timeout as proof of “not processed” and infinitely retry a non-idempotent command. Use provider idempotency keys, status lookups, or reconciliation.

Envelopes help carry the identity for these actions, yet **do not provide cross-service exactly-once effects on their own**.

## 20. Unit Test: `mapPayload` Preserves Metadata While Changing Payload Properly

The best unit tests for Envelope Wrapper check not just that output exists, but **all metadata invariants** and the **new payload type**.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class DeliveryEnvelopeUnitTest {

    private EnvelopeMetadata metadata() {
        return new EnvelopeMetadata(
                1,
                "tenant-a",
                "evt-ship-901",
                "shipping:tenant-a:SHIP-901:7",
                "trace-901",
                "ORDER_SERVICE",
                Instant.parse("2026-11-21T03:00:00Z"));
    }

    private DomainEnvelope<DeliveryRequest> request(
            ServiceLevel level) {
        return new DomainEnvelope<>(
                metadata(),
                new DeliveryRequest("SHIP-901", level, 2));
    }

    @Test
    void standardSubflowPreservesTheEntireEnvelopeMetadata() {
        DomainEnvelope<DeliveryRequest> input =
                request(ServiceLevel.STANDARD);

        DomainEnvelope<DeliveryQuote> output =
                new DeliveryQuoteTransformer().standardQuote(input);

        assertEquals(input.metadata(), output.metadata());
        assertEquals("tenant-a", output.metadata().tenantId());
        assertEquals(
                "evt-ship-901", output.metadata().eventId());
        assertEquals(
                "shipping:tenant-a:SHIP-901:7",
                output.metadata().businessCorrelationKey());
        assertEquals("trace-901", output.metadata().traceId());

        assertEquals(
                ServiceLevel.STANDARD,
                output.payload().serviceLevel());
        assertEquals(
                new BigDecimal("60000"),
                output.payload().amountVnd());
    }

    @Test
    void expressSubflowPreservesMetadataAndComputesPrice() {
        DomainEnvelope<DeliveryRequest> input =
                request(ServiceLevel.EXPRESS);

        DomainEnvelope<DeliveryQuote> output =
                new DeliveryQuoteTransformer().expressQuote(input);

        assertEquals(input.metadata(), output.metadata());
        assertEquals(
                new BigDecimal("160000"),
                output.payload().amountVnd());
        assertEquals("SHIP-901", output.payload().shipmentId());
    }

    @Test
    void theWrongSubflowCannotSilentlyRepriceTheRequest() {
        DomainEnvelope<DeliveryRequest> input =
                request(ServiceLevel.EXPRESS);

        assertThrows(IllegalStateException.class,
                () -> new DeliveryQuoteTransformer()
                        .standardQuote(input));
    }

    @Test
    void inputEnvelopeIsNotMutatedByTransformation() {
        DomainEnvelope<DeliveryRequest> input =
                request(ServiceLevel.STANDARD);
        DeliveryRequest originalPayload = input.payload();
        EnvelopeMetadata originalMetadata = input.metadata();

        new DeliveryQuoteTransformer().standardQuote(input);

        assertSame(originalPayload, input.payload());
        assertSame(originalMetadata, input.metadata());
    }
}
~~~

In immutable record examples, **`assertSame`** on input metadata passes because `mapPayload` keeps the record reference; however, **the critical contract is `assertEquals`** on values. If a future mapper builds an identical immutable copy of metadata, that is not a business bug.

### 20.1. Test Preserving `eventId` on Redelivery

~~~java
// Additional test fragment.
@Test
void repeatedTransformationKeepsLogicalEventIdentity() {
    DomainEnvelope<DeliveryRequest> input =
            request(ServiceLevel.EXPRESS);

    DeliveryQuoteTransformer transformer = new DeliveryQuoteTransformer();
    DomainEnvelope<DeliveryQuote> first =
            transformer.expressQuote(input);
    DomainEnvelope<DeliveryQuote> replay =
            transformer.expressQuote(input);

    assertEquals(
            first.metadata().eventId(),
            replay.metadata().eventId());
    assertEquals(
            first.metadata().businessCorrelationKey(),
            replay.metadata().businessCorrelationKey());
    assertEquals(first.payload(), replay.payload());
}
~~~

This tests **mapping determinism**. It does not prove database side effects executed once, nor does it replace broker redelivery integration tests.

## 21. Integration Test: Router → Subflow → Output Preserves Envelope

JUnit 5 + `spring-test` can spin up a Spring context with **`DeliveryEnvelopeFlowConfig`** from Section 6. To prevent tests from leaking state into one another, each test sends an event to `DirectChannel` and reads the result from `QueueChannel`.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.Instant;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(DeliveryEnvelopeFlowConfig.class)
class DeliveryEnvelopeFlowTest {

    @Autowired
    @Qualifier("envelopeInput")
    MessageChannel input;

    @Autowired
    @Qualifier("quoteOutput")
    QueueChannel results;

    @Autowired
    @Qualifier("rejectedEnvelopeMessages")
    QueueChannel rejected;

    @BeforeEach
    void drainQueues() {
        while (results.receive(0) != null) {
            // Leftover output from prior test.
        }
        while (rejected.receive(0) != null) {
            // Leftover unknown type from prior test.
        }
    }

    private DomainEnvelope<DeliveryRequest> envelope(
            String tenant, String shipment,
            String eventId, ServiceLevel level) {
        EnvelopeMetadata md = new EnvelopeMetadata(
                1,
                tenant,
                eventId,
                "shipping:" + tenant + ":" + shipment + ":7",
                "trace-" + eventId,
                "ORDER_SERVICE",
                Instant.parse("2026-11-21T03:00:00Z"));

        return new DomainEnvelope<>(
                md,
                new DeliveryRequest(shipment, level, 2));
    }

    private void send(DomainEnvelope<?> envelope) {
        assertTrue(input.send(
                EnvelopeMessageFactory.trusted(envelope)));
    }

    private DomainEnvelope<?> nextEnvelope() {
        Message<?> result = results.receive(0);
        assertNotNull(result);
        assertInstanceOf(
                DomainEnvelope.class, result.getPayload());
        return (DomainEnvelope<?>) result.getPayload();
    }

    @Test
    void standardGoesThroughSubflowWithoutLosingMetadata() {
        DomainEnvelope<DeliveryRequest> original =
                envelope(
                        "tenant-a", "SHIP-101",
                        "evt-standard-101", ServiceLevel.STANDARD);

        send(original);
        DomainEnvelope<?> output = nextEnvelope();

        assertEquals(original.metadata(), output.metadata());
        assertInstanceOf(DeliveryQuote.class, output.payload());
        DeliveryQuote quote = (DeliveryQuote) output.payload();
        assertEquals(ServiceLevel.STANDARD, quote.serviceLevel());
        assertEquals(new BigDecimal("60000"), quote.amountVnd());
        assertNull(results.receive(0));
    }

    @Test
    void expressGoesThroughItsOwnSubflow() {
        DomainEnvelope<DeliveryRequest> original =
                envelope(
                        "tenant-a", "SHIP-102",
                        "evt-express-102", ServiceLevel.EXPRESS);

        send(original);
        DomainEnvelope<?> output = nextEnvelope();

        assertEquals(original.metadata(), output.metadata());
        assertEquals(
                new BigDecimal("160000"),
                ((DeliveryQuote) output.payload()).amountVnd());
        assertNull(results.receive(0));
    }

    @Test
    void differentTenantsKeepSeparateBusinessIdentity() {
        DomainEnvelope<DeliveryRequest> tenantA =
                envelope("tenant-a", "SHIP-901",
                        "evt-a", ServiceLevel.STANDARD);
        DomainEnvelope<DeliveryRequest> tenantB =
                envelope("tenant-b", "SHIP-901",
                        "evt-b", ServiceLevel.STANDARD);

        send(tenantA);
        send(tenantB);
        DomainEnvelope<?> first = nextEnvelope();
        DomainEnvelope<?> second = nextEnvelope();

        assertNotEquals(
                first.metadata().businessCorrelationKey(),
                second.metadata().businessCorrelationKey());
        assertEquals("tenant-a", first.metadata().tenantId());
        assertEquals("tenant-b", second.metadata().tenantId());
    }

    @Test
    void unsupportedEnvelopePayloadUsesDefaultRoute() {
        EnvelopeMetadata md = new EnvelopeMetadata(
                1, "tenant-a", "evt-unknown",
                "shipping:tenant-a:SHIP-999:7",
                "trace-unknown", "ORDER_SERVICE",
                Instant.parse("2026-11-21T03:00:00Z"));

        DomainEnvelope<String> unsupported =
                new DomainEnvelope<>(md, "unknown-payload-type");

        send(unsupported);

        Message<?> quarantine = rejected.receive(0);
        assertNotNull(quarantine);
        assertEquals(unsupported, quarantine.getPayload());
        assertNull(results.receive(0));
    }
}
~~~

### 21.1. What Does This Test Prove?

1. The Router picks the right `STANDARD`/`EXPRESS` branch.
2. Subflows return **`DomainEnvelope`** instead of plain `DeliveryQuote`.
3. **Immutable metadata** survives routing, transformation, and convergence.
4. **Tenant, `eventId`, and `businessCorrelationKey`** are never mixed between two requests.
5. Unknown payloads go to the default route and never produce bogus quotes.

### 21.2. What Does This Test Not Yet Prove?

- HTTP/JMS/AMQP/TCP `HeaderMapper` serializes metadata accurately.
- Real trust boundaries authenticate clients/producers.
- Flows can recover after a process restart.
- Retries/acks work properly on broker redelivery.
- Downstream writes to the database exactly once.
- Behavior when two publish/subscribe branches run concurrently.
- Transformer exceptions route to a durable quarantine/DLQ.

Because `DirectChannel` and `QueueChannel` operate in-memory in this example, this test is **not** proof of a distributed workflow with exactly-once or fault-tolerant semantics.

## 22. Test: When Spring Headers and Envelope Metadata Disagree

If a legacy endpoint mutates the `businessCorrelationKey` Spring header without updating envelope metadata, downstream sees two conflicting sources of truth. A boundary validator can catch this condition:

~~~java
import org.springframework.messaging.Message;

final class EnvelopeHeaderConsistency {

    static void requireMatch(Message<DomainEnvelope<?>> message) {
        DomainEnvelope<?> envelope = message.getPayload();
        String expected =
                envelope.metadata().businessCorrelationKey();

        Object header = message.getHeaders()
                .get("businessCorrelationKey");

        if (!(header instanceof String actual)
                || !expected.equals(actual)) {
            throw new SecurityException(
                    "BUSINESS_CORRELATION_MISMATCH");
        }

        Object tenant = message.getHeaders()
                .get("trustedTenantId");
        if (!envelope.metadata().tenantId().equals(tenant)) {
            throw new SecurityException(
                    "TRUSTED_TENANT_MISMATCH");
        }
    }
}
~~~

Test example:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class EnvelopeHeaderConsistencyTest {

    @Test
    void mismatchedHeadersAreRejected() {
        EnvelopeMetadata md = new EnvelopeMetadata(
                1, "tenant-a", "evt-901",
                "shipping:tenant-a:SHIP-901:7",
                "trace-901", "ORDER_SERVICE",
                java.time.Instant.parse("2026-11-21T03:00:00Z"));

        DomainEnvelope<DeliveryRequest> envelope =
                new DomainEnvelope<>(
                        md,
                        new DeliveryRequest(
                                "SHIP-901", ServiceLevel.STANDARD, 2));

        Message<DomainEnvelope<?>> forged =
                MessageBuilder.<DomainEnvelope<?>>withPayload(envelope)
                        .setHeader("trustedTenantId", "tenant-b")
                        .setHeader(
                                "businessCorrelationKey",
                                "shipping:tenant-b:SHIP-901:7")
                        .build();

        assertThrows(SecurityException.class,
                () -> EnvelopeHeaderConsistency.requireMatch(forged));
    }
}
~~~

In production code, place the **header consistency check** at the exact boundary where both fields are expected to exist. Do not require every message across the entire system to carry these headers, since some endpoints/protocols intentionally transmit only the payload envelope; at inbound, rebuild mirrored headers from verified metadata.

## 23. Subflow Errors: Not Every Message Goes to the Default Route

An integration system must distinguish:

| Case | Example | Where detected | Correct behavior |
| --- | --- | --- | --- |
| **Unknown payload type** | Envelope payload is `String` | Router | Route to reject/quarantine |
| **Validation error** | `packageCount=0` | Constructor/ingress | Fail fast with error code |
| **Wrong route** | `EXPRESS` sent to `STANDARD` subflow | Transformer | Fail; never miscalculate price |
| **Header/envelope mismatch** | Differing tenants | Boundary validator | Security rejection/audit |
| **Serialization error** | Unsupported wire schema version | Adapter/converter | Quarantine/unsupported version |
| **Timeout** | Remote provider fails to reply | Gateway/adapter | Follow retry/`UNKNOWN`/reconcile policy |
| **Duplicate event** | Broker redelivers old `eventId` | Inbox/side-effect layer | Idempotent skip or recovery |
| **Application bug** | Code throws `NullPointerException` | Handler | Error flow, alert, fix |

The Router's **`defaultOutputChannel`** branch is only for **unmapped routing keys** in the example. If **`DeliveryQuoteTransformer`** throws an exception, the message does not automatically route to `rejectedEnvelopeMessages`. That is the **error path**, governed by channel/endpoint semantics.

### 23.1. `DirectChannel` and `ExecutorChannel`

- **`DirectChannel`:** invocation usually runs on the sending thread; exceptions can propagate back to the sender. With an inbound HTTP gateway, map errors to a response per contract.
- **`ExecutorChannel`:** handlers can run on another thread; exceptions can emit an **`ErrorMessage`** on `errorChannel` depending on endpoint/framework configuration.
- **Poller/broker adapter:** ack/requeue, retries, and DLQs depend on the inbound adapter and transaction boundaries; there is no single default behavior valid for all brokers.

### 23.2. `ErrorMessage` Is Not an Envelope

An **`ErrorMessage`** carries a `Throwable`, and for some exception types may reference `failedMessage`. Never assume:

~~~text
errorMessage.getPayload() instanceof DomainEnvelope
~~~

is true. Error flows must look up trusted metadata in `failedMessage` or a persistent workflow store if available; if source, tenant, or `eventId` cannot be determined, quarantine **without guessing** `businessCorrelationKey` from a stack trace.

### 23.3. Use Typed Rejection Outcomes When a Terminal Business Result Is Needed

If a subflow cannot compute a quote due to a business rule, emit a typed outcome:

~~~java
sealed interface QuoteOutcome permits QuoteAccepted, QuoteRejected {}

record QuoteAccepted(DeliveryQuote quote)
        implements QuoteOutcome {
}

record QuoteRejected(
        String shipmentId,
        String reasonCode) implements QuoteOutcome {
}
~~~

All outcomes can still be wrapped in **`DomainEnvelope<QuoteOutcome>`** with appropriate metadata. Conversely, an indeterminate DB timeout **is not equivalent** to `QuoteRejected`; apply retry/`UNKNOWN` handling per contract.

### 23.4. Do Not Swallow Errors with a Fake Valid Envelope

Anti-example:

~~~java
// Never do this for indeterminate errors:
catch (Exception ex) {
    return input.mapPayload(
            new DeliveryQuote(
                    input.payload().shipmentId(),
                    ServiceLevel.STANDARD,
                    java.math.BigDecimal.ZERO));
}
~~~

This turns an infrastructure failure or bug into a valid-looking 0 VND quote, potentially picking the wrong `serviceLevel` too. If fallback quotation is ever desired, it requires an explicit business policy, reason, version, and audit trail.

## 24. Versioning Envelopes When Multiple Subflows Deploy Independently

A large system may deploy the router and individual subflows on independent cadences. If subflow A expects metadata schema v1 while subflow B requires v2, changing only the record where envelopes are built can break compatibility.

### 24.1. Three Distinct Version Types

| Version | What it controls | Example |
| --- | --- | --- |
| **Envelope schema version** | Metadata + payload envelope structure | metadata adds `causationId` in v2 |
| **Payload schema version** | Types and fields of `DeliveryRequest`/`Quote` | request adds dimensions/weight |
| **Business rule version** | How prices or taxes are calculated | `tariff-2026-11` |

They **do not have to increment together**. A business tariff change does not require changing the envelope schema if the output payload holds `tariffVersion` or rules are tracked in state.

### 24.2. Ensuring Backward Compatibility

Suppose a new subflow accepts v2 and must temporarily handle v1 messages remaining in the broker:

1. Decode v1/v2 per published `schemaVersion`.
2. Upgrade v1 → v2 in an **upcaster** using semantically valid defaults.
3. Validate new fields; if impossible to infer, reject/quarantine instead of fabricating values.
4. Send only **verified canonical envelopes** into internal subflows.
5. Ensure replaying old events uses the proper mapping version without silently producing different business effects.

Never use default Java serialization across JVM/service versions as a long-term wire contract.

### 24.3. Canary Deployments and Mixed Versions

During rollouts, two instances may receive the same event while running two different subflow mapping versions. If outputs must be deterministic per business rule version, the envelope or workflow state must specify **`tariffVersion`**; otherwise, the same `eventId` can produce a different amount on retry, causing conflicts in the idempotency ledger.

**Immutable metadata does not guarantee immutable business rules.** Manage rule versions/snapshots whenever retries must reproduce identical results.

## 25. Security: An Envelope Is Not an Access Pass

A payload with valid metadata syntax is not automatically allowed into any subflow. Minimum security boundary:

1. **Authenticate:** know who the producer is.
2. **Authorize:** is the producer authorized for that tenant, shipment, event type, and workflow epoch?
3. **Validate:** schema, types, sizes, enums, timestamps, and origin.
4. **Bind:** construct `DomainEnvelope` from registry/verified identity, never trusting client claims alone.
5. **Route:** pick subflows from verified data; never let clients specify arbitrary `MessageChannel` names.
6. **Persist/dedup:** guard against replay and event collisions.
7. **Audit:** log just enough with controlled access and retention.

### 25.1. Do Not Route by Client-Supplied Channel Names

~~~json
{
  "destination": "internalPaymentAdminChannel",
  "payload": {"shipmentId": "SHIP-901"}
}
~~~

If an endpoint turns `destination` directly into a header/channel name, clients can reach unauthorized flows. Use an **allowlisted business route key** such as validated `STANDARD`/`EXPRESS` enums, then map them to internal channel beans in the Router.

### 25.2. Do Not Copy External Spring Control Headers

Headers like `replyChannel`, `errorChannel`, `routingSlip`, or custom control fields can steer execution paths. At the trust boundary, build a new Message using an **explicit allowlist** rather than `copyHeaders(rawHeaders)` from unauthenticated HTTP/JMS/TCP inputs.

### 25.3. `TraceId` Is Neither a Secret Nor Authority

`TraceId` helps correlate logs, yet clients can forge trace headers. Validate trace context and restrict log access; never use `traceId` as a business idempotency key or proof of tenant ownership.

### 25.4. Avoid Leaking Payloads via Error Logs

If an envelope holds addresses, payment details, or PII:

- Never log full envelopes by default at `DEBUG`/`ERROR`.
- Mask/sanitize error details and log only `eventRef`, `source`, `stage`, and `reason`.
- Quarantine payloads in access-controlled storage with retention and audited access.
- When building alerts/metrics, avoid using raw `businessCorrelationKey`/`eventId` as high-cardinality labels.

## 26. Observing Whether Subflows Drop Metadata

A request may pass the Router and reach a handler successfully, yet fail later with “Missing tenant”. Counting only aggregate inbound/outbound totals makes it hard to tell which hop dropped metadata.

| Metric | Purpose |
| --- | --- |
| **`envelope_ingress_accepted_total{source}`** | Verified envelopes |
| **`envelope_routed_total{branch}`** | Messages routed to `STANDARD`/`EXPRESS` |
| **`envelope_route_rejected_total{reason}`** | Unknown types, unsupported business routes |
| **`envelope_transform_success_total{branch}`** | Subflows completing successfully |
| **`envelope_transform_failure_total{branch,reason}`** | Validation/transform errors |
| **`envelope_metadata_mismatch_total{reason}`** | Header vs. envelope key/tenant mismatch |
| **`envelope_wire_roundtrip_failure_total{protocol}`** | Schema errors or fields lost during serialization |
| **`envelope_retry_total{branch}`** | Retry counts |
| **`envelope_duplicate_skipped_total{branch}`** | Deduplicated by logical event |
| **`envelope_output_duration_seconds{branch}`** | Latency per branch |
| **`envelope_quarantine_total{reason}`** | Events needing investigation |
| **`envelope_active_operations`** | Pending/in-flight work |

Metric labels should come from a **bounded set of values**. Never use arbitrary `eventId`, `tenantId`, `shipmentId`, `traceId`, or `businessCorrelationKey` as labels. Use structured logs/tracing to locate specific events.

### 26.1. Sample Ingress Log

~~~json
{
  "stage": "verified-ingress",
  "eventRef": "evt-ship-901",
  "envelopeVersion": 1,
  "routeCandidate": "EXPRESS",
  "source": "ORDER_SERVICE",
  "outcome": "ACCEPTED"
}
~~~

### 26.2. Sample Subflow Log

~~~json
{
  "stage": "express-quote-subflow",
  "eventRef": "evt-ship-901",
  "traceRef": "trace-901",
  "envelopeVersion": 1,
  "outputType": "DeliveryQuote",
  "outcome": "SUCCESS"
}
~~~

### 26.3. Sample Mismatch Log

~~~json
{
  "stage": "envelope-consistency",
  "eventRef": "evt-ship-901",
  "reason": "BUSINESS_CORRELATION_MISMATCH",
  "outcome": "REJECTED"
}
~~~

These are **application log examples**; Spring Integration does not emit these exact fields automatically. To instrument `MessageChannel`s/endpoints, use interceptors, Micrometer, and tracing instrumentation compatible with your deployment version.

### 26.4. Warning Signals

- `STANDARD` outputs exceed ingress due to redeliveries without deduplication.
- `EXPRESS` inputs rise while `quoteOutput` stays flat.
- Metadata mismatches appear after adding a Transformer that returns a full `Message`.
- Unknown payload types spike after a partner schema upgrade.
- Pending groups grow because a Splitter/Filter drops children while an Aggregator waits for the full count.
- Queue age/processing latency rises after switching from `DirectChannel` to async channels.
- HTTP callbacks arrive yet Gateways time out because `replyChannel` wiring is broken.
- Replays after restarts trigger duplicate side effects.

## 27. Runbook: Message Traverses Subflow Yet Loses Correlation

**Scenario:** Router logs “EXPRESS route selected”, Transformer logs “quote generated”, yet downstream reports missing `businessCorrelationKey` or processes the wrong tenant.

### Step 1 — Verify the Envelope Right at Ingress

Check whether the request was authenticated, whether tenant/shipment/epoch came from a trusted registry, and whether `eventId` is stable. Never start by minting a new `correlationId` downstream.

### Step 2 — Inspect Router Output

Did the message enter the right branch channel? Was the route key read from the **validated payload** or from a client-supplied header? If the route key is unsupported, the message must go to reject/quarantine.

### Step 3 — Inspect Transformer Input and Output

Compare:

~~~text
Before:
  Message.payload = DomainEnvelope<DeliveryRequest>

After:
  Message.payload = ?
~~~

If output is plain **`DeliveryQuote`**, the subflow unwrapped the application envelope. If output is a `DomainEnvelope` with altered metadata, check whether the mapper minted a fresh `UUID`, `Instant.now()`, or `source`.

### Step 4 — Inspect Spring Message Headers

If metadata remains in `DomainEnvelope` while the `businessCorrelationKey` header vanished, consider having the boundary mapper rebuild mirrored headers **from the trusted envelope**. If metadata and headers conflict, reject rather than picking arbitrarily.

Check whether a handler returned a **new `Message`** that dropped required `replyChannel` or sequence headers.

### Step 5 — Inspect the Transport Boundary

If the message traversed HTTP/JMS/AMQP/TCP, check whether the converter serialized only the inner payload, whether `HeaderMapper` mapped selected fields, and whether inbound rebuilt the envelope from a verified wire contract.

### Step 6 — Check Splitter/Gateway Scope

If the flow uses a Splitter, separate the subgroup's **technical `CORRELATION_ID`** from the parent business key. If it uses a Gateway, separate the invocation's **temporary `replyChannel`** from the durable group key.

### Step 7 — Check Timeouts, Retries, and Duplicates

A late reply arriving after a Gateway timeout can still be valid business-wise; do not route it to a closed temporary channel. A redelivered event keeping the same `eventId` must be caught by the inbox/ledger and never applied twice.

### Step 8 — Recover

- **Missing metadata due to mapper bug:** fix the mapper/contract and run a controlled replay with the stable `eventId`.
- **Header spoofing or tenant mismatch:** quarantine and raise a security alert; never manually force it into the “right” group.
- **Unknown envelope schema:** deploy a versioned converter or reject with audit.
- **Partial workflow:** inspect manifest, child outcomes, group timeouts, and persistent state.
- **External effect `UNKNOWN`:** reconcile before retrying.

### Step 9 — Verify After the Fix

Trace one event from ingress to `quoteOutput`: identical tenant, `eventId`, business key, and trace context; payload transformed accurately; Spring headers consistent; downstream commits strictly per idempotency policy.

## 28. Test Matrix for Envelopes Across Subflows

| Test case | Input or scenario | Key assertion |
| --- | --- | --- |
| Standard path | `STANDARD`, two packages | 60,000 VND quote, metadata preserved |
| Express path | `EXPRESS`, two packages | 160,000 VND quote, metadata preserved |
| Two tenants | Same `shipmentId`, different tenants | Two distinct business keys |
| Same logical retry | Same input/`eventId`, second send | `eventId`/correlation metadata unchanged |
| Unsupported payload | Unknown `DomainEnvelope` payload type | Default reject channel, no quote produced |
| Wrong subflow | `EXPRESS` sent to `StandardTransformer` | Explicit failure |
| Header mismatch | Header `tenant-b`, envelope `tenant-a` | Rejected at consistency boundary |
| Unwrap regression | Transformer returns plain `DeliveryQuote` | Downstream test catches missing envelope |
| Double wrapping | Uncontracted `Envelope<Envelope<Request>>` | Rejected / type validation fails |
| Child identity | Split into 3 parcels | 3 stable child IDs, parent link retained |
| Duplicate child | One parcel redelivered | Not counted as a fourth child |
| Splitter sequencing | Multiple child messages | `CORRELATION_ID`/`SEQUENCE_SIZE` match child group |
| Scatter-Gather | Three independent providers | Releases once unique outcomes arrive |
| Gateway reply | Caller awaits one quote | Routes to right `replyChannel` invocation |
| Late reply | Caller times out, callback arrives later | Handled per business workflow policy |
| Wire roundtrip | Serialize/deserialize across transport | Contract metadata preserved |
| Forged tenant | Client self-claims `tenant-admin` | Ingress rejects untrusted metadata |
| Schema mismatch | Envelope version 99 | Reject/quarantine, never guess format |
| Async handoff | `ExecutorChannel` replaces `DirectChannel` | Tenant resolved without `ThreadLocal` |
| Restart | In-flight operation in persistent store | Recovers exact identity |
| Redelivery after commit | Broker sends old event | No duplicate side effect |

### 28.1. Wire Contract Test

A real HTTP/JMS/AMQP/TCP test should:

1. Construct a **verified envelope** inside the application.
2. Serialize per a supported wire format version.
3. Send through the adapter using the real configured header mapper/converter.
4. Receive at the far boundary, parse, and authenticate the source.
5. Assert **`tenant`/`eventId`/`businessKey`/`schemaVersion`** match after round-trip.
6. Assert live `replyChannel`/`errorChannel` objects are neither serialized nor restored.

Do not call `ObjectMapper` directly and label it a “JMS `HeaderMapper` test”; test the **transport boundary** itself when verifying adapter behavior.

### 28.2. Concurrency Test

Run multiple events for the same tenant and across different tenants concurrently, mixing `STANDARD` and `EXPRESS`. Assert outputs by `eventId`/`businessKey` rather than expecting arrival order. If using an Aggregator, test with a shared store/locking or partition ownership, especially across multiple instances.

### 28.3. Do Not Conflate Error Tests

An unknown payload is sent by the Router to the reject channel, whereas a Transformer mapping failure throws an exception or routes to `errorChannel`. Those two cases require **two distinct assertions**; never assume every error falls into the Router's `defaultOutputChannel`.

## 29. Practice Exercise: Envelope Across Three Subflows

Extend the pricing example to three branches:

- **`STANDARD`:** computes base pricing.
- **`EXPRESS`:** adds express surcharge.
- **`INTERNATIONAL`:** looks up geographic zone, weight, and customs policy before pricing.

Unified input:

~~~json
{
  "metadata": {
    "schemaVersion": 1,
    "tenantId": "tenant-a",
    "eventId": "evt-delivery-400",
    "businessCorrelationKey": "delivery:tenant-a:SHIP-400:2",
    "traceId": "trace-delivery-400",
    "sourceSystem": "ORDER_SERVICE",
    "receivedAt": "2026-11-21T03:00:00Z"
  },
  "payload": {
    "shipmentId": "SHIP-400",
    "serviceLevel": "INTERNATIONAL",
    "packageCount": 3,
    "weightGrams": 1500
  }
}
~~~

### 29.1. Technical Requirements

1. Define immutable `EnvelopeMetadata`, typed payloads, and `schemaVersion`.
2. Verify tenant + shipment + workflow epoch before sending to trusted `envelopeInput`.
3. Define `RouteKey` using an allowlisted enum, never arbitrary channel names from HTTP clients.
4. Use a Router to pick among the three subflows; each subflow **returns a new `DomainEnvelope`**.
5. Preserve `eventId`, business key, and source/`receivedAt` when only changing representation.
6. For `INTERNATIONAL`, if a handler calls an external service, apply explicit timeout/retry/`UNKNOWN` policies.
7. If the result emits a new `QUOTE_CREATED` event, mint a derived/causation identity rather than silently copying `eventId`.
8. Create a shared `commonQuoteOutput` channel and a common invariant validator.
9. Add separate error/quarantine paths for unknown routes, invalid amounts, and infrastructure failures.
10. Add idempotent business persistence after unwrapping at a controlled boundary.

### 29.2. Testing Requirements

| Scenario | Expected result |
| --- | --- |
| Valid `STANDARD` | Accurate quote payload, original metadata intact |
| Valid `EXPRESS` | Accurate quote payload, original metadata intact |
| Valid `INTERNATIONAL` | Quote carries `tariffVersion` and accurate amount/currency |
| Spoofed `serviceLevel` name | Rejected/unsupported; never routes to other internal channels |
| `eventId` redelivery | No duplicate side effects |
| Spoofed `tenantId` | Trusted envelope is never built |
| Transformer returns plain payload | Contract test catches lost envelope |
| Message headers differ from metadata | Boundary validator rejects |
| Remote pricing timeout | Never turns `UNKNOWN` into a 0 price |
| Multiple async requests | Correlation independent of thread or arrival order |
| Subflow emits a derived event | Includes `parentEventId`/`causationId` |
| Unsupported wire version | Quarantined, never arbitrarily deserialized |

### 29.3. Bonus: Fan-Out to Three Carriers

After building an `INTERNATIONAL` request, send it in parallel to three shipping providers and Gather the responses:

~~~mermaid
flowchart LR
    E["Envelope<InternationalRequest>"] --> S["Scatter"]
    S --> A["Provider A"]
    S --> B["Provider B"]
    S --> C["Provider C"]
    A --> G["Gather unique provider outcomes"]
    B --> G
    C --> G
    G --> R["Envelope<ShippingDecision>"]
~~~

Require **distinct derived event identity per provider**, accurate `businessCorrelationKey` per shipment/epoch, per-provider operation deduplication, and ensure timeouts never treat an `UNKNOWN` result as `APPROVED`. If the Aggregator needs all three outcomes, check **unique provider IDs**, not merely `group.size() == 3`.

### 29.4. Completion Criteria

Someone reading downstream code can process **`DomainEnvelope<DeliveryQuote>`** without needing to know:

- Whether the earlier request went through the `STANDARD` or `EXPRESS` subflow.
- Whether the Router used named channels or inline `subFlowMapping`.
- Which HTTP/JMS/AMQP adapter brought the request to ingress.
- Whether the subflow ran on the same thread.

Downstream still **knows the tenant, logical `eventId`, business correlation, payload type, and `schemaVersion`** from one unified contract. Only when business rules require service-level-specific policy does it read `serviceLevel` from the payload, without hunting through connector-specific headers.

## 30. Self-Check Questions

1. What problem does EIP Envelope Wrapper solve when a message traverses multiple subflows?
2. Are `DomainEnvelope` and Spring `Message` the same wrapper layer?
3. Why should a `replyChannel` object not be placed inside an application wire envelope?
4. Which metadata does `mapPayload()` preserve, and what does it change?
5. What breaks if a Transformer returns a plain `DeliveryQuote` when downstream expects `DomainEnvelope`?
6. May a subflow mint a new `eventId` on every retry? When is minting a new `eventId` correct?
7. Why must `businessCorrelationKey` be scoped by tenant and workflow epoch?
8. Does `sourceSystem` inside an envelope prove the producer is trustworthy?
9. Why might an envelope with a Java record for metadata still lack deep immutability?
10. How do Router `subFlowMapping` and named channels differ in code organization?
11. Does a Router's default route automatically catch exceptions thrown by a Transformer?
12. How does a Gateway's temporary `replyChannel` differ from `businessCorrelationKey`?
13. Why can an HTTP callback arriving after a Gateway timeout not reply directly to the old Java invocation?
14. When a Splitter creates three parcel tasks, should all three share the parent's `eventId`?
15. Why can a Splitter's technical `CORRELATION_ID` differ from `businessCorrelationKey`?
16. Does Publish-Subscribe automatically wait for all subscribers to finish and return one result?
17. How should a Message with Spring header `tenant-a` and `DomainEnvelope` metadata `tenant-b` be handled?
18. What happens if an outbound adapter converter serializes only `envelope.payload`?
19. Is an HTTP `HeaderMapper` an authorization mechanism?
20. Why can `ThreadLocal`/MDC not serve as the source of business identity in async subflows?
21. Should a redelivery preserve the original `receivedAt` and `eventId`?
22. Why does a successful Kafka/JMS ack not prove the business side effect committed?
23. When do you need an inbox/outbox instead of an in-JVM `Set` remembering `eventId`s?
24. In Scatter-Gather, how do `correlationStrategy` and `releaseStrategy` differ in responsibility?
25. If a provider callback arrives late after a final decision, should it automatically overwrite the prior result?
26. Why should you avoid minting a new UUID on each retry if you want idempotency?
27. When schema v1 is replayed while subflows expect v2, how should upcasting work?
28. Which metrics help pinpoint a subflow dropping metadata without creating high-cardinality labels?
29. Can an immutable metadata record be shared across concurrent subflows? Under what condition on the payload?
30. Why does code passing a `DirectChannel` test not prove safe execution across brokers and multiple instances?

## 31. Pre-Deployment Checklist

- **`DomainEnvelope`** is clearly separated from Spring `Message` and transport envelopes.
- Metadata carries `schemaVersion`, tenant/event/correlation identities, and explicit provenance.
- Envelopes and payloads are immutable or use defensive copies.
- Rules specify which metadata is preserved on transforms and when derived event identities are created.
- Tenant and workflow are verified at ingress before creating trusted envelopes.
- `businessCorrelationKey` includes proper tenant, entity, and workflow epoch scopes.
- Router picks branches via allowlisted enums, never client-supplied channel names.
- Both `STANDARD` and `EXPRESS` subflows return **`DomainEnvelope`** with a shared payload type.
- Downstream never guesses schemas from connector-specific headers.
- Any Transformer returning a new `Message` defines a propagation strategy for required runtime headers.
- When Spring headers mirror domain metadata, a validator catches mismatches.
- Raw `replyChannel`/`errorChannel`/`routingSlip` headers are never copied from external messages.
- Live `MessageChannel`s or arbitrary Java objects are never serialized as wire contracts.
- `HeaderMapper`/`MessageConverter` behavior for each HTTP/JMS/AMQP/TCP adapter is tested.
- Unwrapping occurs only at controlled boundaries with sufficient tenant/correlation/idempotency context.
- Splitters mint stable child identities when children are distinct logical events.
- Technical child-group correlation and parent business keys are never conflated.
- Publish-subscribe never shares mutable objects across concurrent subscribers.
- Scatter-Gather enforces unique-member release policies and appropriate timeouts.
- Sync Gateways use `replyChannel` only for the active request lifecycle.
- Async callbacks rely on persistent business identity rather than expired temporary channels.
- Retries preserve stable event IDs/business keys; attempt IDs may vary.
- Downstream side effects implement idempotency/transactions/reconciliation.
- Inbox/outbox/recovery close crash windows between receipt and dispatch.
- Async channels use bounded pools/queues and never rely on `ThreadLocal` for business identity.
- Aggregator flows define group metadata retention/reaping and late-arrival policies.
- Envelope schema evolution has versioning, upcasters, compatibility tests, and rollout plans.
- Unknown payload types are rejected/quarantined; Transformer errors follow a dedicated error path.
- Logs/metrics never leak sensitive data and avoid high-cardinality labels.
- Tests cover standard/express, tenant/epoch, metadata, header mismatches, unknown types, derived child IDs, retries, wire round-trips, and restarts.
- Runbooks trace envelope loss from ingress → Router → Transformer → adapter → downstream.

## 32. Conclusion

**Passing envelopes through subflows** is more than forwarding payloads from channel A to channel B. You must preserve a **context contract** so branches can process independently while returning results tied to the right tenant, event, and workflow. A clean design typically looks like:

~~~text
Verified ingress
  -> DomainEnvelope<DeliveryRequest>
  -> Router
      -> standardSubflow -> mapPayload(DeliveryQuote)
      -> expressSubflow  -> mapPayload(DeliveryQuote)
  -> DomainEnvelope<DeliveryQuote>
  -> common validation / idempotent downstream
~~~

For a **transformation of the same logical event**, keeping metadata via **`mapPayload`** avoids arbitrarily regenerating `eventId`, `correlationId`, or `traceId`. For **fan-out/Splitters producing new events**, deliberately mint child identities and causation links. For **Gateways**, keep `replyChannel` at the runtime layer; for **adapters**, enforce versioned, authenticated wire envelopes and header mappings; and for **retries**, preserve business identity to prevent duplicate side effects.

This design lets Spring Integration combine Router, Transformer, Splitter, Aggregator, Gateway, retry, and error channels while preserving **message semantics** across every subflow—not just Java types.

## References

- [Enterprise Integration Patterns — Envelope Wrapper](https://www.enterpriseintegrationpatterns.com/patterns/messaging/EnvelopeWrapper.html): principles of wrapping a message in a context-bearing structure across integration boundaries.
- [Enterprise Integration Patterns — Message Translator](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessageTranslator.html): transforming message structure or representation.
- [Enterprise Integration Patterns — Correlation Identifier](https://www.enterpriseintegrationpatterns.com/patterns/messaging/CorrelationIdentifier.html): linking messages and replies belonging to the same task.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): building `IntegrationFlow`, routing, subflows, and channels.
- [Spring Integration Reference — Routers](https://docs.spring.io/spring-integration/reference/router.html): message-driven routing, default output channels, and routing semantics.
- [Spring Integration Reference — Transformer](https://docs.spring.io/spring-integration/reference/transformer.html): POJO transformers, input/output Messages, and header propagation.
- [Spring Integration Reference — Message](https://docs.spring.io/spring-integration/reference/message.html): Spring `Message` and `MessageHeaders`.
- [Spring Integration Reference — Splitter](https://docs.spring.io/spring-integration/reference/splitter.html): child messages and sequence/correlation metadata.
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): correlation groups, release strategies, timeouts, and late arrivals.
- [Spring Integration Reference — Publish-Subscribe Channels](https://docs.spring.io/spring-integration/reference/channel/implementations.html): channel semantics and subscriber delivery.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): temporary `replyChannel` and request/reply lifecycles.
- [Spring Integration Reference — HTTP Support](https://docs.spring.io/spring-integration/reference/http.html): HTTP inbound/outbound adapters and gateways.
- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): JMS adapters, protocol correlation, and header mapping.
- [Spring Integration Reference — TCP Message Correlation](https://docs.spring.io/spring-integration/reference/ip/correlation.html): TCP gateways, cooperating adapters, connection IDs, and metadata transfer.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `errorChannel`, `ErrorMessage`, and sync/async errors.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): preventing duplicate messages and side-effect considerations.

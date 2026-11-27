# Routing Invalid Messages to Quarantine

## 1. The Problem: Where Should Invalid Messages Go?

A system receives order events via a message broker. Every event must have an order ID, event ID, valid amount, and supported currency. In practice, however, producers may send data missing fields, with broken structure, incompatible schema versions, or violating business rules.

~~~text
OrderSubmitted(
  eventId = "EVT-101",
  orderId = "ORD-101",
  amountVnd = -100000,
  currency = "VND"
)
~~~

If this message goes straight to the Payment Handler, the handler may miscalculate or call external systems with invalid data. If a **Message Filter** drops the message **without a trace**, operations teams have no idea which producer failed, how many orders were affected, or how to recover after fixing the bug.

**Quarantine** is a dedicated handling path for data that fails defined criteria. Rather than continuing into the main business flow, the message is routed to a controlled destination to **preserve evidence, record reasons, monitor, and decide whether to fix, replay, or discard**.

~~~mermaid
flowchart LR
    P["Producer / Adapter"] --> V["Validate"]
    V --> F{"Message Filter"}
    F -->|Valid| B["Business Flow"]
    F -->|Invalid| Q["Quarantine Flow"]
    Q --> S[("Quarantine Store")]
    S --> O["Review / Fix / Authorized Replay"]
    O -->|New controlled attempt| V
~~~

Within the `SPRING_INTEGRATION_PATTERN` module, this lesson belongs to the **Message filter and validation** chapter. The module's scope is implementing Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows; combining Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation, and testing/observing processing branches.

### Goals

After this lesson, you will be able to:

1. Distinguish **invalid messages** from **technical failures**, **retryable failures**, **business rejections**, and **poison messages**.
2. Design validation that produces **structured reason codes**, not just a `true/false` boolean.
3. Use Spring Integration Java DSL to send valid messages to the business flow and invalid messages to quarantine via **Filter + discard channel**.
4. Retain sufficient metadata for investigation without exposing sensitive data.
5. Choose appropriate storage, acknowledgment, deduplication, retention, and recovery mechanisms for quarantine.
6. Build a **review → fix root cause → revalidate → replay** workflow with authorization, auditing, and limits.
7. Write JUnit tests proving invalid messages **never reach business handlers** and **are not silently dropped**.

## 2. "Invalid" Means Different Things

Not every failed message should end up in the same error queue with the same retry policy.

| Situation | Example | Classification | Typical handling |
|---|---|---|---|
| **Malformed wire payload** | Truncated JSON, undecodable bytes. | Parse/deserialization error. | Error flow or adapter/DLQ preserving a safe raw reference. |
| **Schema invalid** | Missing `orderId` or wrongly typed field. | Contract/schema violation. | Quarantine to inspect producer/schema version. |
| **Business validation invalid** | `amountVnd <= 0`, unsupported currency. | Rule violation. | Quarantine or final rejection per contract. |
| **Unauthorized** | Tenant lacks permission to emit events. | Security/authorization rejection. | Block before business flow, security audit, limit returned details. |
| **Transient dependency failure** | Database unreachable. | Infrastructure failure. | Retry/backoff/circuit breaker; do not label payload invalid. |
| **Business rejection outcome** | Insufficient stock despite valid request. | Business result. | Return rejected outcome per flow; do not quarantine by default. |
| **Poison message** | Consistently crashes consumer on every read. | May be malformed, unsupported schema, or bug. | DLQ/quarantine after classification; investigate. |
| **Valid duplicate** | Broker redelivers an already-processed event. | Idempotency/delivery. | Return stored outcome or acknowledge safely; do not treat as invalid. |

**Key decision:** Quarantine holds messages **with problems requiring separate handling**, not a catch-all dumping ground for every `Exception`. A database call timing out does not suddenly make `amountVnd` in the message wrong.

### 2.1. Validation at Different Boundaries

~~~text
Raw bytes
   |
   v
Decode / schema validation
   |
   v
Authentication & authorization
   |
   v
Typed message
   |
   v
Business validation
   |
   +-- valid ----> business processing
   |
   +-- invalid --> quarantine
~~~

The exact ordering may vary by adapter and trust boundary. For instance, signatures sometimes must be verified on **raw bytes before parsing**. Never use this diagram as an excuse to skip required security checks.

### 2.2. A Filter Cannot Filter an Undeserialized Payload

If JSON has an `amountVnd` field shaped as an object that cannot map to `BigDecimal`, the inbound adapter may throw **before** creating an `OrderSubmitted` message. At that point, the Filter expecting typed payloads **has never run**.

Therefore, you must design an **error path** at the parse/adapter boundary, distinct from the business Filter's discard path:

~~~mermaid
flowchart TD
    R["Raw broker record"] --> D{"Decodable?"}
    D -->|No| E["Adapter / deserialization error handling"]
    E --> Q1["Raw-error quarantine / DLQ"]
    D -->|Yes| V{"Business validation"}
    V -->|Valid| B["Business handler"]
    V -->|Invalid| Q2["Typed-message quarantine"]
~~~

Spring Integration's `errorChannel` can receive `ErrorMessage`s in properly configured execution contexts, yet **do not assume all parse errors automatically flow into the global `errorChannel`**. Deserializers and adapter containers may have their own error handlers, recoverers, or DLQs. Verify how errors surface on the exact transport your project uses.

## 3. Differences Between Filter, Router, Error Channel, and Quarantine

| Component | Responsibility | What it does not do automatically |
|---|---|---|
| **Message Filter** | Lets a message pass or rejects it via a predicate. | Does not automatically persist a durable quarantine record. |
| **Discard Channel** | Receives messages rejected by Filter when configured. | Does not automatically define retention/replay/auditing. |
| **Content-Based Router** | Picks one/more channels based on content. | Does not inherently know a message is "invalid". |
| **Transformer** | Converts payload/format; can produce a Validation Outcome. | Does not retry failures or write to stores. |
| **Error Channel** | Handling path for certain technical errors per configuration. | Does not replace validation outcomes or rejection policies. |
| **Dead-Letter Queue (DLQ)** | Holds records undeliverable at the transport/consumer layer. | Does not necessarily contain business-rule field violations. |
| **Quarantine Flow** | Persists, isolates, tracks, and orchestrates handling of invalid messages. | Does not guarantee payload validity after replay. |

An easily testable construction is:

~~~text
Typed Input
   -> Transformer (computes violations + policyVersion exactly once)
   -> Filter (valid? YES/NO)
        YES -> accepted business flow
        NO  -> discardChannel("orders.quarantine")
~~~

You do not need to call the Filter an error handler: **`false`** is a normal routing decision. Conversely, failures in the validator itself or the quarantine store are technical exceptions handled under your failure policy.

### 3.1. Do Not Accidentally Enable `throwExceptionOnRejection`

In a Spring Integration Filter, a **discard path** and **throwing an exception on rejection** have different behaviors. If `throwExceptionOnRejection(true)` is enabled, an invalid message may raise an exception instead of going solely to the discard flow as intended.

In this lesson, the Filter **does not throw merely because business validation returned false**; we configure an explicit discard channel. Unexpected errors like quarantine persistence failures must still be detected and never swallowed.

### 3.2. Quarantine Does Not Have to Be a Broker Topic

It can be:

- A channel pointing to a service writing a **database record**.
- A durable queue/topic consumed by a quarantine manager.
- An object store for raw payloads + metadata database.
- A review workflow with states, permissions, audits, expiration, and replay tooling.

**Naming a channel `quarantine` does not create durability.** `DirectChannel` simply dispatches per its semantics; if the handler only appends to an in-memory `List`, data is lost on JVM restart. The Java code below uses a fake store for learning and testing, not as a complete production design.

## 4. Validation Contracts Need More Than a Boolean

### 4.1. Returning Only `false` Loses the Root Cause

A simple predicate:

~~~java
boolean valid(OrderSubmitted order) {
    return order.amountVnd() != null
            && order.amountVnd().signum() > 0
            && "VND".equals(order.currency());
}
~~~

The Filter rejects the message, yet the quarantine operator has no idea **which field failed**, which rule version applied, or whether it can be fixed and replayed. The solution is building a structured **Validation Outcome** and filtering on that outcome.

### 4.2. Violations with Stable Codes

A useful outcome:

~~~json
{
  "policyVersion": "orders-v1",
  "valid": false,
  "issues": [
    {"code": "AMOUNT_MUST_BE_POSITIVE", "field": "amountVnd"},
    {"code": "UNSUPPORTED_CURRENCY", "field": "currency"}
  ]
}
~~~

**Do not embed sensitive data inside reason strings.** Instead of printing raw `customerEmail`, tokens, or payment details into violations, use field paths and error codes so review UIs/workflows can enforce proper read permissions.

### 4.3. Fields to Keep Alongside Invalid Messages

| Field | Why is it needed? | Notes |
|---|---|---|
| `quarantineId` | Identifies the quarantine store record. | Does not replace the business event ID. |
| `sourceSystem` | Identifies which producer needs fixing. | Source must be authenticated, not merely trusted from payload. |
| `tenantScope` | Maintains tenant isolation. | Derived from trusted ingress/security context. |
| `eventId` or `ingressEnvelopeId` | Deduplicates redeliveries of the same input. | Must stay stable across retries per policy. |
| `validationPolicyVersion` | Explains why an older version rejected it. | Revalidation may change outcomes when policy evolves. |
| `issues` | List of violated rules/fields. | Avoid PII/raw secrets in reason text. |
| `receivedAt` | Tracks group/quarantine age. | Use a reliable clock and consistent timezone. |
| `payloadReference`/checksum | Preserves original for investigation/replay. | Enforce encryption, retention, and integrity. |
| `state` | NEW, UNDER_REVIEW, FIXED, REPLAYED, DISCARDED… | Use authorized transitions and auditing. |
| `attemptId`, `replayOf` | Traces revalidation/replay attempts. | Do not conflate attempts with business operations. |
| `traceId`/`correlationId` | Links logs across flows. | Do not use as the sole dedupe key. |

**Storing the original is a security decision.** Retain only enough data for investigation/replay, respecting permissions, retention, and personal data regulations. For many invalid messages, a protected payload reference suffices instead of copying contents into logs.

## 5. Establishing Trusted Ingress Metadata Before Filtering

Separate the **business payload** from **metadata issued by trusted ingress**. This separation is especially vital when the payload is malformed or lacks an `eventId`.

~~~text
IngressEnvelope
  envelopeId         = EV-ING-202
  authenticatedTenant= TENANT-A
  trustedSource      = oms
  payload            = OrderSubmitted(...)
~~~

In this demo, `envelopeId` is a stable ID **issued/recovered by the trusted adapter** for the same logical input. When the broker redelivers that message, `envelopeId` must **remain unchanged** to deduplicate quarantine cases on this ID. If an adapter generates a fresh UUID on every delivery, it is no longer a reliable dedupe identity; use a source event ID or durable ingress mapping instead.

### 5.1. Do Not Derive Trust from an Invalid Payload

Wrong:

~~~text
Incoming JSON: {"tenantId": "TENANT-B", ...}
Quarantine tenant scope: read directly from that JSON
~~~

If an attacker or bug supplies the wrong `tenantId`, the record could be filed under another tenant. Tenant scope must come from the principal, broker authentication, configured route, or another trusted source; payload contents are only cross-checked when necessary.

### 5.2. What If There Is No `eventId` Yet?

You cannot build an idempotency key solely from a missing `eventId` field. You can use a **trusted envelope identity** or sustainably propagated transport record coordinates, while understanding their semantics:

- A broker offset is stable when redelivering **that exact record**.
- If an event is republished as a new record, its offset changes.
- Payload hashes may collide between two valid identical events or shift due to canonicalization.
- A UUID generated each time a consumer receives a message **cannot deduplicate redeliveries**.

Therefore, define the **quarantine idempotency scope** based on the data source rather than guessing from malformed JSON.

## 6. Java Domain Model: Immutable Outcomes and Reason Codes

Examples target **Java 17+, Spring Boot 3.x, Spring Integration 6.x**. Types are assumed to reside in the same package; in real projects, split `public` classes/records into separate files per Java rules. They serve learning purposes and do not replace your project's security policies or schema registry.

### 6.1. Orders Can Violate Rules, Yet Messages Need Non-Null Payloads

~~~java
import java.math.BigDecimal;

record OrderSubmitted(
        String eventId,
        String orderId,
        BigDecimal amountVnd,
        String currency,
        String customerEmail) {
    // No validation in constructor so business-invalid data
    // can be represented after decoding.
}
~~~

Spring `Message` does not allow `null` payloads, yet we can represent a **missing order object** inside a trusted envelope. Nullable fields on `OrderSubmitted` are inputs for the validator to judge, not a recommendation for validated domain entities.

### 6.2. Envelope with Trusted Origin

~~~java
record IngressOrder(
        String envelopeId,
        String authenticatedTenant,
        String trustedSource,
        OrderSubmitted order) {

    IngressOrder {
        if (envelopeId == null || envelopeId.isBlank()
                || authenticatedTenant == null
                || authenticatedTenant.isBlank()
                || trustedSource == null || trustedSource.isBlank()) {
            throw new IllegalArgumentException(
                    "INVALID_TRUSTED_INGRESS_METADATA");
        }
    }
}
~~~

In the demo, we **assume the adapter already authenticated** `authenticatedTenant` and `trustedSource`. Having a Java record accept a `String` does not make that `String` trustworthy. Production must bind the source from the security principal/adapter configuration and verify cross-tenant access before storing or replaying.

### 6.3. Validation Outcome

~~~java
import java.util.List;
import java.util.Objects;

record ValidationIssue(String code, String field) {
    ValidationIssue {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException(
                    "INVALID_VALIDATION_REASON");
        }
    }
}

record ValidationOutcome(
        IngressOrder ingress,
        List<ValidationIssue> issues,
        String policyVersion) {

    ValidationOutcome {
        Objects.requireNonNull(ingress, "ingress");
        issues = List.copyOf(issues);
        if (policyVersion == null || policyVersion.isBlank()) {
            throw new IllegalArgumentException(
                    "INVALID_POLICY_VERSION");
        }
    }

    boolean valid() {
        return issues.isEmpty();
    }
}
~~~

A `ValidationOutcome` retains the **original typed envelope** alongside the issue list. When the Filter rejects, the discard channel receives **that exact outcome** to persist reasons. If the Filter only saw a boolean and downstream recomputed validation, both checks could diverge when policies change or validators depend on external state.

### 6.4. Deterministic, Easily Tested Validation Policy

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

final class OrderValidationPolicy {
    static final String VERSION = "orders-v1";
    private static final Set<String> TRUSTED_SOURCES =
            Set.of("oms", "portal");
    private static final BigDecimal MAX_AMOUNT =
            new BigDecimal("1000000000");

    ValidationOutcome validate(IngressOrder ingress) {
        List<ValidationIssue> issues = new ArrayList<>();

        // Source allowlist is an illustrative data policy,
        // NOT a replacement for adapter authentication.
        if (!TRUSTED_SOURCES.contains(ingress.trustedSource())) {
            issues.add(new ValidationIssue(
                    "UNSUPPORTED_SOURCE", "trustedSource"));
        }

        OrderSubmitted order = ingress.order();
        if (order == null) {
            issues.add(new ValidationIssue(
                    "ORDER_PAYLOAD_MISSING", "order"));
            return new ValidationOutcome(
                    ingress, issues, VERSION);
        }

        if (missing(order.eventId())) {
            issues.add(new ValidationIssue(
                    "EVENT_ID_REQUIRED", "eventId"));
        }
        if (missing(order.orderId())) {
            issues.add(new ValidationIssue(
                    "ORDER_ID_REQUIRED", "orderId"));
        }
        if (order.amountVnd() == null
                || order.amountVnd().signum() <= 0) {
            issues.add(new ValidationIssue(
                    "AMOUNT_MUST_BE_POSITIVE", "amountVnd"));
        } else if (order.amountVnd().compareTo(MAX_AMOUNT) > 0) {
            issues.add(new ValidationIssue(
                    "AMOUNT_EXCEEDS_LIMIT", "amountVnd"));
        }
        if (!"VND".equals(order.currency())) {
            issues.add(new ValidationIssue(
                    "UNSUPPORTED_CURRENCY", "currency"));
        }

        return new ValidationOutcome(ingress, issues, VERSION);
    }

    private static boolean missing(String value) {
        return value == null || value.isBlank();
    }
}
~~~

The thresholds and allowlists in the demo are illustrative only. Do not apply `MAX_AMOUNT=1_000_000_000` in a real system without an explicit business policy. Here `customerEmail` is not validated; if required by business rules, add a versioned rule, but **never record raw email addresses in violation codes or logs**.

### 6.5. Example Input Producing Multiple Issues

~~~java
IngressOrder input = new IngressOrder(
        "ING-1001",
        "TENANT-A",
        "oms",
        new OrderSubmitted(
                "EVT-1001",
                "",
                new BigDecimal("-100000"),
                "USD",
                "sensitive@example.com"));

ValidationOutcome outcome =
        new OrderValidationPolicy().validate(input);

// outcome.valid() == false
// issues: ORDER_ID_REQUIRED,
//         AMOUNT_MUST_BE_POSITIVE,
//         UNSUPPORTED_CURRENCY
~~~

**Why capture multiple issues?** An operator can fix all wrong fields in one pass instead of fixing one, replaying, and discovering the next error. Still, for highly sensitive data or potential abuse, you may limit the number of issues and displayed details based on permissions.

## 7. Store Quarantine as an Orchestrated State, Not Just a Log

### 7.1. Minimal Record

~~~text
quarantineId:        Q-abc
ingressEnvelopeId:   ING-1001
tenant:              TENANT-A
source:              oms
policyVersion:       orders-v1
reasonCodes:         [ORDER_ID_REQUIRED, AMOUNT_MUST_BE_POSITIVE]
status:              NEW
firstSeenAt:         ...
payloadReference:    protected-ref
replayAttempt:       0
~~~

A **quarantine record** has its own identity/metadata. Do not use `MessageHeaders.ID` as the sole record key because messages can be rebuilt on adapter redelivery; nor treat `quarantineId` as a downstream payment idempotency key.

### 7.2. Quarantine Case Lifecycle States

~~~mermaid
stateDiagram-v2
    [*] --> NEW
    NEW --> UNDER_REVIEW: take case
    UNDER_REVIEW --> FIX_APPROVED: authorized correction
    UNDER_REVIEW --> DISCARDED: approved permanent discard
    FIX_APPROVED --> REPLAY_REQUESTED: create controlled attempt
    REPLAY_REQUESTED --> REVALIDATING: send to validation ingress
    REVALIDATING --> REPLAYED: validation + business handoff accepted
    REVALIDATING --> UNDER_REVIEW: still invalid
    NEW --> EXPIRED: retention policy
    REPLAYED --> [*]
    DISCARDED --> [*]
    EXPIRED --> [*]
~~~

This is an **application-proposed state machine**, not a feature auto-generated by Spring Integration. "REPLAYED" should be defined carefully: it might only mean the message was re-dispatched, **not that business side effects committed**. If completion proof is needed, attach a separate business outcome/receipt.

### 7.3. Quarantine Differs from a Dead Letter Queue

| Criterion | Business quarantine | Transport DLQ |
|---|---|---|
| Input source | Validation false, rejected schema/rule. | Consumer/adapter processing failure per retry policy. |
| Primary data | Reason code, policy version, typed/raw reference. | Record, headers, exception/attempt metadata. |
| Handler | Data steward, producer owner, workflow operator. | Messaging/platform operator and application. |
| Replay | Revalidate after fix/authorization. | Redrive per broker/app policy; still requires revalidation. |
| TTL/retention | Driven by data sensitivity, privacy, and review process. | Driven by broker/platform retention. |

A DLQ can serve as the **storage infrastructure for quarantine** if it has adequate metadata, security, and workflow support. Conversely, you can store quarantine in a DB and use a DLQ strictly for transport failures. Never assume those two names carry identical semantics across every system.

### 7.4. Why Not Send the Entire Payload to Logs?

Quarantine must aid investigation without becoming a data leak vector:

- **Logs:** masked keys, reason codes, route, source, policy version, trace; avoid PII/raw credentials.
- **Protected storage:** original payload or reference to the original, with encryption, access control, retention, and integrity checks.
- **Review UI:** display only necessary fields per role; never expose everything to all operators by default.
- **Replay:** read from the original source/verified corrected revision; never copy raw error text back as payload.

When schemas are huge, keep object references and checksums instead of duplicating data repeatedly. Still, protect that reference as a capability pointing to sensitive data.

## 8. Illustrative Quarantine Repository: Idempotency on Redelivery

If the broker redelivers the same invalid message, do not endlessly create new quarantine records. You need a **stable key** and a policy when the same key arrives with different content.

### 8.1. Keyed by Source and Envelope Identity

~~~java
record QuarantineKey(
        String tenant,
        String source,
        String envelopeId) {}
~~~

In the demo code, `envelopeId` is issued by trusted ingress and preserved across redeliveries of the same message. The key excludes `deliveryAttempt` because retries belong to the **same quarantine case**.

When intentionally revalidating under a new policy or an approved payload fix, create a **new attempt/revision with clear lineage** rather than silently overwriting the original record under the same key. The original state/payload should remain for auditing per retention policy.

### 8.2. Case Record Preserving Original Typed Data

~~~java
import java.time.Instant;

record QuarantineCase(
        String quarantineId,
        QuarantineKey key,
        ValidationOutcome originalOutcome,
        String state,
        Instant createdAt) {}
~~~

In production, `originalOutcome` may be replaced with a **protected payload reference** and sanitized structured violations; holding the original object in memory in the demo is neither secure nor durable for sensitive data.

### 8.3. In-Memory Store for Unit/Integration Tests

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

final class InMemoryQuarantineStore {
    private final ConcurrentMap<QuarantineKey, QuarantineCase> cases =
            new ConcurrentHashMap<>();
    private final Clock clock;

    InMemoryQuarantineStore(Clock clock) {
        this.clock = clock;
    }

    QuarantineCase store(ValidationOutcome outcome) {
        if (outcome.valid()) {
            throw new IllegalArgumentException(
                    "VALID_MESSAGE_CANNOT_BE_QUARANTINED");
        }
        IngressOrder ingress = outcome.ingress();
        QuarantineKey key = new QuarantineKey(
                ingress.authenticatedTenant(),
                ingress.trustedSource(),
                ingress.envelopeId());

        return cases.compute(key, (ignored, existing) -> {
            if (existing != null) {
                if (!existing.originalOutcome().equals(outcome)) {
                    throw new IllegalStateException(
                            "QUARANTINE_IDENTITY_CONFLICT");
                }
                return existing; // Identical redelivery of existing case.
            }
            return new QuarantineCase(
                    UUID.randomUUID().toString(),
                    key,
                    outcome,
                    "NEW",
                    Instant.now(clock));
        });
    }

    int count() {
        return cases.size();
    }

    List<QuarantineCase> snapshot() {
        return List.copyOf(cases.values());
    }
}
~~~

**Why compare `originalOutcome`?** A buggy producer might reuse an `envelopeId` for **two different payloads**. Merely calling `putIfAbsent` and returning the old case would drop the second record without a trace. The demo throws `QUARANTINE_IDENTITY_CONFLICT` to expose the hazard. Production can record a dedicated conflict case and quarantine both rather than just throwing; protect access and preserve full evidence.

**Limitations of the fake:** `ConcurrentHashMap.compute` is atomic per key within one JVM, yet provides no durable storage, DB transactions, cross-pod concurrency, encryption, status workflows, cleanup, or replay. Production should use unique constraints/CAS and transactional inbox/outbox across real transport boundaries.

### 8.4. Why Not Delete Invalid Messages Right After Logging?

If an inbound record is ACKed as soon as a log line is emitted, log rotation/deletion or node crashes can erase investigation evidence. Whenever zero data loss is required, ACK only **after** the quarantine store or durable queue confirms persistence per policy.

If the quarantine store fails, do not catch the exception and return `send=true` as if persistence succeeded. Enforce bounded retries/backpressure/transport redelivery and failure observability.

## 9. Spring Integration Java DSL: Filter with Discard Channel

### 9.1. Components in the Demo

~~~text
orders.validation.input
  -> OrderValidationPolicy.validate(...)
  -> ValidationOutcome
  -> Message Filter [outcome.valid()]
       true  -> orders.valid      -> AcceptedOrderProbe
       false -> orders.quarantine -> InMemoryQuarantineStore
~~~

Because the Transformer creates `ValidationOutcome` **once**, quarantine receives all violations. The Filter's predicate only checks `outcome.valid()` without re-running validation rules.

### 9.2. Probe on the Valid Branch

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

final class AcceptedOrderProbe {
    private final List<IngressOrder> accepted =
            new CopyOnWriteArrayList<>();

    void record(IngressOrder envelope) {
        accepted.add(envelope);
    }

    List<IngressOrder> snapshot() {
        return List.copyOf(accepted);
    }
}
~~~

The probe is for testing only. It is **not a production payment/order business handler** and has no transactions. When replacing it with a real handler, apply event/operation idempotency, retries, and proper acknowledgments.

### 9.3. Complete Flow Configuration

~~~java
import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class QuarantineRoutingConfiguration {

    @Bean(name = "orders.validation.input")
    MessageChannel validationInput() {
        return new DirectChannel();
    }

    @Bean(name = "orders.valid")
    MessageChannel validOrders() {
        return new DirectChannel();
    }

    @Bean(name = "orders.quarantine")
    MessageChannel quarantineOrders() {
        return new DirectChannel();
    }

    @Bean
    OrderValidationPolicy orderValidationPolicy() {
        return new OrderValidationPolicy();
    }

    @Bean
    AcceptedOrderProbe acceptedOrderProbe() {
        return new AcceptedOrderProbe();
    }

    @Bean
    InMemoryQuarantineStore quarantineStore() {
        return new InMemoryQuarantineStore(Clock.systemUTC());
    }

    @Bean
    IntegrationFlow validateAndRouteOrders(
            OrderValidationPolicy validator) {
        return IntegrationFlow.from("orders.validation.input")
                .transform(IngressOrder.class, validator::validate)
                .filter(
                        ValidationOutcome.class,
                        ValidationOutcome::valid,
                        spec -> spec.discardChannel(
                                "orders.quarantine"))
                .channel("orders.valid")
                .get();
    }

    @Bean
    IntegrationFlow processValidOrders(AcceptedOrderProbe probe) {
        return IntegrationFlow.from("orders.valid")
                .handle(ValidationOutcome.class,
                        (outcome, headers) -> {
                            probe.record(outcome.ingress());
                            return null; // Terminal demo handler.
                        })
                .get();
    }

    @Bean
    IntegrationFlow captureInvalidOrders(
            InMemoryQuarantineStore store) {
        return IntegrationFlow.from("orders.quarantine")
                .handle(ValidationOutcome.class,
                        (outcome, headers) -> {
                            store.store(outcome);
                            return null; // Terminal demo handler.
                        })
                .get();
    }
}
~~~

### 9.4. Reading the DSL Accurately

1. `IntegrationFlow.from("orders.validation.input")` receives an `IngressOrder` that has passed the trusted adapter.
2. `transform(IngressOrder.class, validator::validate)` builds a `ValidationOutcome` with the original payload and issue list.
3. `filter(ValidationOutcome.class, ValidationOutcome::valid, ...)` evaluates the **already-computed outcome**.
4. If valid, the Filter forwards the message to `orders.valid`.
5. If invalid, `discardChannel("orders.quarantine")` routes the rejected message to the quarantine channel.
6. `captureInvalidOrders` writes a case to the fake store without calling the business handler.
7. `DirectChannel`s give the demo synchronous dispatch and simple testing; they do not provide durability across restarts.

For Spring Integration 6.x, the example uses common Java DSL overloads. When integrating into a specific version, check overload signatures, `FilterEndpointSpec`, and the behavior of the adapters/channels used—especially discard, error handling, and transactions. **There is no build/test evidence for the project at this STEP 4.**

### 9.5. Why Not Use `filter(order -> valid(order))` and Skip Discard?

If you only write:

~~~java
// Anti-pattern if the application must persist invalid messages.
.filter(IngressOrder.class, order ->
        validator.validate(order).valid())
~~~

a `false` predicate removes the message from the business flow **without sending it to quarantine** if no discard is configured. Moreover, only a boolean remains without reason codes. In flows requiring auditing/replay, you need a discard route whose handler persists durably and is observable.

### 9.6. Discard Is Not a Default Exception

An invalid order is **classified bad data**, not necessarily a Java handler failure. You do not need to throw an exception to create a quarantine record. Exceptions suit other validation contracts, yet they enter error flows **depending on the execution model** and do not automatically populate fields like `policyVersion` or `issues`.

### 9.7. What If the Discard/Quarantine Handler Throws?

With `DirectChannel` in the demo, an exception from `store.store(outcome)` propagates back to the caller of `send(...)`. In a broker consumer/poller, errors may be routed to an error handler per adapter configuration. Either way, never consider a message durably quarantined if the write fails.

To isolate latency, you can place a durable queue ahead of the quarantine writer. Yet **successful enqueueing differs from persisting the case**: define acknowledgment checkpoints, retry/DLQ, and monitoring for each layer.

## 10. Unit Testing the Validator Before Wiring the Framework

### 10.1. A Valid Order Has Zero Violations

~~~java
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTrue;

class OrderValidationPolicyHappyPathTest {
    private final OrderValidationPolicy validator =
            new OrderValidationPolicy();

    @Test
    void acceptedOrderHasNoIssues() {
        IngressOrder incoming = new IngressOrder(
                "ING-1",
                "TENANT-A",
                "oms",
                new OrderSubmitted(
                        "EVT-1",
                        "ORD-1",
                        new BigDecimal("100000"),
                        "VND",
                        "private@example.com"));

        ValidationOutcome result = validator.validate(incoming);

        assertTrue(result.valid());
        assertTrue(result.issues().isEmpty());
    }
}
~~~

This unit test only proves the Java validator's rules; it **does not** prove Spring Filter routing or quarantine persistence.

### 10.2. One Input Can Produce Multiple Reason Codes

~~~java
import java.math.BigDecimal;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class OrderValidationPolicyInvalidTest {
    private final OrderValidationPolicy validator =
            new OrderValidationPolicy();

    @Test
    void returnsAllKnownViolations() {
        IngressOrder incoming = new IngressOrder(
                "ING-2", "TENANT-A", "oms",
                new OrderSubmitted(
                        "", "", new BigDecimal("-500"),
                        "USD", "private@example.com"));

        ValidationOutcome result = validator.validate(incoming);

        assertFalse(result.valid());
        Set<String> reasonCodes = result.issues().stream()
                .map(ValidationIssue::code)
                .collect(Collectors.toSet());

        assertEquals(Set.of(
                "EVENT_ID_REQUIRED",
                "ORDER_ID_REQUIRED",
                "AMOUNT_MUST_BE_POSITIVE",
                "UNSUPPORTED_CURRENCY"), reasonCodes);
        assertEquals("orders-v1", result.policyVersion());
    }
}
~~~

### 10.3. Missing Business Payload While Trusted Envelope Exists

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class OrderMissingPayloadTest {
    @Test
    void missingOrderInEnvelopeHasStructuredReason() {
        IngressOrder incoming = new IngressOrder(
                "ING-3", "TENANT-A", "oms", null);

        ValidationOutcome result =
                new OrderValidationPolicy().validate(incoming);

        assertFalse(result.valid());
        assertEquals("ORDER_PAYLOAD_MISSING",
                result.issues().get(0).code());
    }
}
~~~

This is a Java object whose envelope holds `order=null`. For **completely undecodable raw JSON**, you cannot construct a typed `IngressOrder` to run this test; test the error handler at the inbound adapter instead.

## 11. Integration Test: Invalid Messages Are Truly Quarantined

### 11.1. Testing Across Filter and Both Handlers

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(QuarantineRoutingConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class QuarantineRoutingIntegrationTest {

    @Autowired
    @Qualifier("orders.validation.input")
    MessageChannel input;

    @Autowired
    AcceptedOrderProbe accepted;

    @Autowired
    InMemoryQuarantineStore quarantine;

    private void send(IngressOrder envelope) {
        assertTrue(input.send(
                MessageBuilder.withPayload(envelope).build(),
                1_000));
    }

    @Test
    void validOrderGoesToBusinessButNotQuarantine() {
        send(new IngressOrder(
                "ING-11", "TENANT-A", "oms",
                new OrderSubmitted(
                        "EVT-11", "ORD-11",
                        new BigDecimal("200000"),
                        "VND", "private@example.com")));

        assertEquals(1, accepted.snapshot().size());
        assertEquals(0, quarantine.count());
    }

    @Test
    void invalidOrderGoesToQuarantineNotBusiness() {
        send(new IngressOrder(
                "ING-12", "TENANT-A", "oms",
                new OrderSubmitted(
                        "EVT-12", "ORD-12",
                        new BigDecimal("-1000"),
                        "VND", "private@example.com")));

        assertEquals(0, accepted.snapshot().size());
        assertEquals(1, quarantine.count());

        QuarantineCase stored = quarantine.snapshot().get(0);
        assertEquals("ING-12", stored.key().envelopeId());
        assertEquals("orders-v1",
                stored.originalOutcome().policyVersion());
        assertEquals("AMOUNT_MUST_BE_POSITIVE",
                stored.originalOutcome()
                        .issues().get(0).code());
    }
}
~~~

**What the test proves:** the Filter rejects the message properly, `discardChannel` has a handler, the quarantine handler receives the outcome with reason codes, and the accepted probe is not called.

**What the test does not prove:** persistence across restarts, broker acks, adapter header mapping, encryption, retention, replay, or tenant authorization. The fake store is in-memory only.

### 11.2. Redelivering the Same Invalid Envelope Does Not Create Two Cases

~~~java
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(QuarantineRoutingConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class QuarantineDuplicateIntegrationTest {

    @Autowired
    @Qualifier("orders.validation.input")
    MessageChannel input;

    @Autowired
    InMemoryQuarantineStore quarantine;

    @Autowired
    AcceptedOrderProbe accepted;

    @Test
    void duplicateInvalidEnvelopeKeepsOneCase() {
        IngressOrder same = new IngressOrder(
                "ING-20", "TENANT-A", "oms",
                new OrderSubmitted(
                        "EVT-20", "ORD-20",
                        BigDecimal.ZERO,
                        "VND", null));

        assertTrue(input.send(
                MessageBuilder.withPayload(same).build()));
        assertTrue(input.send(
                MessageBuilder.withPayload(same).build()));

        assertEquals(1, quarantine.count());
        assertEquals(0, accepted.snapshot().size());
    }
}
~~~

Note: the test sends two **distinct Spring Messages** sharing the same trusted envelope ID. It simulates duplicate/redelivery of the same input; do **not** assume every broker preserves `MessageHeaders.ID` across redeliveries.

### 11.3. Same Envelope ID with Different Content Must Be Detected

~~~java
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(QuarantineRoutingConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class QuarantineIdentityConflictTest {

    @Autowired
    @Qualifier("orders.validation.input")
    MessageChannel input;

    @Autowired
    InMemoryQuarantineStore quarantine;

    @Test
    void sameEnvelopeIdWithDifferentPayloadIsNotSilentDuplicate() {
        IngressOrder first = new IngressOrder(
                "ING-30", "TENANT-A", "oms",
                new OrderSubmitted("EVT-30", "ORD-30",
                        new BigDecimal("-1"), "VND", null));

        IngressOrder conflicting = new IngressOrder(
                "ING-30", "TENANT-A", "oms",
                new OrderSubmitted("EVT-30", "ORD-30",
                        new BigDecimal("-2"), "VND", null));

        assertTrue(input.send(
                MessageBuilder.withPayload(first).build()));

        // Spring may wrap store errors in a messaging exception;
        // test checks for failure without relying on wrapper text.
        assertThrows(RuntimeException.class, () ->
                input.send(
                        MessageBuilder.withPayload(conflicting).build()));

        assertEquals(1, quarantine.count());
    }
}
~~~

In production, you must **persist evidence of the conflict** for investigation rather than merely throwing and retrying infinitely. You can open a separate conflict case under another key, route through a secure error path, or use a history/version table with unique constraints. The demo chooses **fail closed** to avoid silent overwrites.

### 11.4. Why Do Tests Need `@DirtiesContext`?

`AcceptedOrderProbe` and `InMemoryQuarantineStore` hold state across messages inside the Spring context. Each integration test should get a fresh context or explicitly reset the store/probe. Otherwise, one test may see cases left over from a prior test and report misleading results.

### 11.5. Testing Async Flows

With an `ExecutorChannel`, broker, or poller:

- Do not assert right after `send` that the quarantine store durably persisted the case.
- Use `CountDownLatch`, `BlockingQueue.poll(timeout)`, or an await mechanism with a deadline.
- Verify **milestones**: accepted, persisted, acked, reviewed, and replayed are distinct states.
- Test full queues, dispatchers without subscribers, worker exceptions, and retry behavior.
- Shut down executors and release latches in `finally` to avoid flaky hangs from `Thread.sleep`.

## 12. Malformed JSON: Errors Can Happen Before the Filter

### 12.1. When the Deserializer Cannot Build `IngressOrder`

Suppose a producer sends:

~~~json
{
  "eventId": "EVT-40",
  "orderId": "ORD-40",
  "amountVnd": {"unexpected": "object"},
  "currency": "VND"
}
~~~

If the inbound adapter fails to deserialize `amountVnd` into `BigDecimal`, the **typed Filter never sees `OrderSubmitted`**. Configuring `discardChannel("orders.quarantine")` on the Filter **does not automatically catch deserialization failures**.

Options depending on the adapter:

1. Catch errors in the inbound consumer's **deserializer/error handler**.
2. Send raw record references, transport coordinates, schema versions, and sanitized error codes to **raw-error quarantine** or a DLQ.
3. Define ack/retry semantics so records are not lost before error records are durably stored.
4. Enforce policies limiting raw payload size and sensitive data.
5. Once the schema/producer is fixed, replay from an authorized source through the same validation ingress.

### 12.2. Do Not Assume Every Exception Goes to `errorChannel`

Spring Integration provides `ErrorMessage` and error channels when endpoints/adapters are configured appropriately. Yet failures in:

- Kafka deserializers/containers,
- JMS message conversion,
- HTTP request-body binding,
- Spring Integration Transformers,
- Quarantine handlers,
- or business endpoints

can follow **different paths**. Never write a single global error handler and claim it covers everything. Write integration tests for each specific adapter.

### 12.3. Error Payloads and Safe Information

Target format:

~~~text
quarantineKind = RAW_PARSE_ERROR
sourceSystem   = configured producer identity
tenantScope    = derived from trusted security context
transportRef   = topic/partition/offset (or equivalent ID)
rawPayloadRef  = encrypted object reference
errorCode      = JSON_TO_ORDER_DESERIALIZATION_FAILED
parserVersion  = v2
receivedAt     = ...
~~~

Avoid:

~~~text
reason = "Cannot deserialize full payload: {...full customer data...}"
~~~

Parser errors and stack traces can accidentally contain PII and secrets. Detailed exceptions can reside in a retention-bound secure diagnostics store, while standard metrics and logs should stick to **finite error classes and codes**.

### 12.4. A Separate Technical Error Path

~~~mermaid
flowchart LR
    A["Inbound Adapter"] -->|typed message| V["Validation Flow"]
    A -->|conversion exception| H["Adapter error handler"]
    H --> E["Safe parse failure metadata"]
    E --> Q[("Raw Quarantine Store / DLQ")]
    V -->|invalid rule| B[("Business Quarantine Store")]
    V -->|valid| P["Business Handler"]
~~~

The two stores do not have to be completely separate; they can be two case kinds in the same quarantine system. What is mandatory is that **reasons, provenance, replay strategies, and access controls are never blurred**.

## 13. Durable Quarantine: Recording Failures Is Also a Side Effect

### 13.1. What Happens When the Store Is Unavailable?

~~~text
T1  Broker delivers invalid message.
T2  Validator detects AMOUNT_MUST_BE_POSITIVE.
T3  Filter sends to discard channel.
T4  Quarantine DB times out.
T5  Consumer must decide whether to ack or retry.
~~~

If the consumer **acks even though the quarantine write failed**, the message can vanish from both the business flow and quarantine. If the consumer **refuses to ack and retries forever**, backlogs grow and producers/consumers stall. Define a clear policy:

- Bounded retries for **transient persistence failures**.
- Backoff, circuit breaker, or pausing intake when the store is down.
- Protected fallback error/DLQ routes where appropriate.
- Monitor counts of messages **validated invalid yet unpersisted**.
- Never flip invalid messages to valid just to "save" throughput.
- If no safe store is available, fail closed / reject intake per agreed SLO.

### 13.2. At-Least-Once Ack/Persist Ordering

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant F as Validation/Filter
    participant Q as Durable Quarantine
    B->>C: Invalid message
    C->>F: Validate
    F-->>C: INVALID + reason codes
    C->>Q: Persist case (idempotency key)
    Q-->>C: Durable commit acknowledged
    C-->>B: Ack original delivery
    Note over B,C: Crash before ack may redeliver
    B->>C: Duplicate delivery
    C->>Q: Upsert same quarantine identity
    Q-->>C: Existing case
    C-->>B: Ack duplicate
~~~

This is a **logical ordering pattern**, not an atomic transaction spanning DB and broker. If the DB commits yet the broker ack is lost, duplicates will arrive: the quarantine writer must be **idempotent**. If the queue/adapter has its own transaction or different offset commit semantics, verify behavior per adapter.

### 13.3. Persistent Quarantine Record: Example Table Design

~~~sql
CREATE TABLE invalid_message_cases (
    quarantine_id      VARCHAR(100) PRIMARY KEY,
    tenant_scope       VARCHAR(100) NOT NULL,
    source_system      VARCHAR(100) NOT NULL,
    ingress_event_id   VARCHAR(200) NOT NULL,
    validation_version VARCHAR(80) NOT NULL,
    reason_codes_json  TEXT NOT NULL,
    payload_reference  TEXT,
    payload_sha256     VARCHAR(64),
    case_status        VARCHAR(40) NOT NULL,
    created_at         TIMESTAMP NOT NULL,
    updated_at         TIMESTAMP NOT NULL,
    UNIQUE (tenant_scope, source_system, ingress_event_id)
);
~~~

**This is an illustrative SQL skeleton**, not a complete production schema. Depending on your DB, JSON columns, transaction isolation, tenant row-level security, and index strategies will vary. If you need multiple **payload revisions/revalidations** for the same ingress event, split **case identity** and **attempt/history** tables rather than letting a unique key block legitimate replays.

### 13.4. Unique Keys Alone Do Not Solve Everything

A unique constraint reduces duplicate cases, yet does not answer:

- Where is the conflict kept if the same key carries a different payload?
- Do two concurrent transactions creating a case handle races cleanly?
- If the payload object was saved but the DB insert failed, how is the orphan object cleaned up?
- If the DB case committed before the object reference was ready, can consumers read the payload?
- Does a fixed business replay retain the original per retention policy?

When data spans an **object store and a database**, it becomes a **dual-write** problem. You may need staging/object versioning, checksums, outboxes/reconcilers, and orphan cleanup to prevent cases with metadata but missing payload data.

### 13.5. Retention Must Reflect Data Sensitivity

| State | Retention considerations to decide |
|---|---|
| NEW, unreviewed | Enforce review SLAs and nearing-expiry alerts. |
| UNDER_REVIEW | Keep data as long as review policy requires, not indefinitely. |
| REPLAYED | Retain metadata/tombstone and receipt; prune payload if allowed. |
| DISCARDED | Keep minimal reason/approval; purge payload per policy. |
| EXPIRED | Run cleanup and audit; prevent automatic replay past expiration. |
| Security rejected | Separate retention and permissions; hide payload from general operators. |

A quarantine store stuffed with PII/credentials is a major liability. Keeping data longer is not inherently better: follow data minimization, encryption, access control, auditing, and deletion policies.

## 14. Replay Is Not "Just Push the Message Back In"

### 14.1. Five Steps of Controlled Replay

A safe workflow:

1. **Review:** identify why it failed validation and who owns the data.
2. **Correction:** fix at the producer/source or create a corrected revision with provenance; never silently overwrite the original record.
3. **Authorization:** verify the operator/service is authorized to replay for that tenant and business operation.
4. **Revalidation:** run the current or explicitly designated versioned policy; record the **new result**.
5. **Dispatch:** only if validation passes, send to the business flow with proper idempotency keys, auditing, and acknowledgments.

~~~mermaid
flowchart TD
    Q[("Quarantine Case")] --> R{"Authorized review?"}
    R -->|No| STOP["Keep quarantined / deny"]
    R -->|Yes| F["Correct source or versioned payload"]
    F --> V["Revalidate under selected policy"]
    V -->|Invalid| AGAIN["New review attempt with reasons"]
    V -->|Valid| I{"Business operation already processed?"}
    I -->|Yes| OLD["Record existing outcome; no duplicate effect"]
    I -->|No / safe| D["Controlled dispatch"]
    D --> AUDIT["Audit attempt and result"]
~~~

### 14.2. Never Call Business Handlers Directly to Bypass Validation

An anti-pattern:

~~~text
Quarantine UI -> "Force replay"
  -> BusinessHandler.handle(rawOriginal)
~~~

This can feed the exact same invalid data back into processing or create duplicate side effects. If a workflow supports an **approved override**, override permissions, reasons, data snapshots, and blast radius must be explicitly defined—never treat it as default replay.

### 14.3. Distinguish Original Event, Correction, and Replay Attempt

~~~text
originalEventId = EVT-200
quarantineId    = Q-200
originalVersion = 1

authorizedCorrection:
  correctedRevisionId = REV-2
  replayAttemptId     = ATT-2
  replayOf            = Q-200
  validationPolicy    = orders-v2
~~~

Roles of each ID:

- **Original identity:** traces back to the rejected data.
- **Correction version:** tracks what changed and by whom.
- **Replay attempt:** tracks each re-entry into the flow.
- **Business idempotency key:** protects side effects if the operation already completed.

**Do not use `replayAttemptId` as a brand-new `operationId`** if you are merely retrying the same payment/order operation. Conversely, if the correction genuinely creates a new operation, require explicit business approval and a new key.

### 14.4. Replaying Under a Newer Policy Can Change Outcomes

For example:

~~~text
T1: orders-v1 did not accept currency USD
    -> Quarantine: UNSUPPORTED_CURRENCY

T2: orders-v2 allows USD with new FX validation
    -> Revalidate original under policy v2
    -> May pass if new fields and authorization are satisfied
~~~

Never treat "quarantined invalid" as permanent regardless of policy changes. Yet never silently **rewrite the policy on an old record** without versioning: you must know which rules applied when it arrived and why.

### 14.5. Prevent Infinite Quarantine → Replay → Quarantine Loops

Enforce:

- Maximum replay attempts and appropriate backoff.
- Conditions waiting for actual correction or policy updates.
- `REPLAY_REJECTED`/`STILL_INVALID` states when nothing was fixed.
- Quotas/operator permissions and poison message alerts.
- A **`quarantineOf`** or lineage field distinguishing original cases from attempts.

**Deterministic invalid payloads** replayed unchanged almost always fail again. Infinite retries never synthesize missing data.

## 15. Source-Bounded Revalidation Example

### 15.1. A Small Policy Checking Replay Readiness

This example only checks **replay preconditions**. It **does not write to a DB**, **does not dispatch to the business flow**, and **does not replace production authorization enforcement**.

~~~java
final class ReplayReviewPolicy {
    private final OrderValidationPolicy validator;

    ReplayReviewPolicy(OrderValidationPolicy validator) {
        this.validator = validator;
    }

    ValidationOutcome revalidate(
            QuarantineCase original,
            IngressOrder corrected,
            boolean authorizationGranted) {

        // This flag comes from a trusted authorization step
        // in the exercise, NEVER from client/JSON input.
        if (!authorizationGranted) {
            throw new SecurityException("REPLAY_NOT_AUTHORIZED");
        }
        if (!original.key().tenant().equals(
                    corrected.authenticatedTenant())
                || !original.key().source().equals(
                    corrected.trustedSource())) {
            throw new SecurityException("REPLAY_SCOPE_MISMATCH");
        }
        if (!"NEW".equals(original.state())
                && !"UNDER_REVIEW".equals(original.state())) {
            throw new IllegalStateException(
                    "REPLAY_STATE_NOT_ALLOWED");
        }

        // Revalidate without mutating originalOutcome.
        return validator.validate(corrected);
    }
}
~~~

In production, `authorizationGranted` must come from a **trusted authorization service** with verified actor IDs and permissions. You also need CAS/state transitions so two operators cannot replay the same case concurrently, ensuring corrections bind to the right original event, tenant, and business operation, and recording audits before dispatching.

### 15.2. Fixing the Amount and Revalidating

~~~java
import java.math.BigDecimal;
import java.time.Clock;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTrue;

class QuarantineRevalidationTest {
    @Test
    void approvedCorrectionCanPassValidation() {
        OrderValidationPolicy validator =
                new OrderValidationPolicy();
        IngressOrder originalInput = new IngressOrder(
                "ING-100", "TENANT-A", "oms",
                new OrderSubmitted(
                        "EVT-100", "ORD-100",
                        new BigDecimal("-10"),
                        "VND", null));

        InMemoryQuarantineStore store =
                new InMemoryQuarantineStore(Clock.systemUTC());
        QuarantineCase originalCase =
                store.store(validator.validate(originalInput));

        IngressOrder corrected = new IngressOrder(
                "ING-100-REV-2", "TENANT-A", "oms",
                new OrderSubmitted(
                        "EVT-100", "ORD-100",
                        new BigDecimal("100000"),
                        "VND", null));

        ValidationOutcome result =
                new ReplayReviewPolicy(validator)
                        .revalidate(originalCase, corrected, true);

        assertTrue(result.valid());
        // This is only revalidation: business handler has not been called.
    }
}
~~~

### 15.3. No Permission, No Replay

~~~java
import java.math.BigDecimal;
import java.time.Clock;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;

class QuarantineReplayAuthorizationTest {
    @Test
    void correctionFromDifferentTenantIsRejected() {
        OrderValidationPolicy validator =
                new OrderValidationPolicy();
        InMemoryQuarantineStore store =
                new InMemoryQuarantineStore(Clock.systemUTC());

        QuarantineCase originalCase = store.store(
                validator.validate(new IngressOrder(
                        "ING-200", "TENANT-A", "oms",
                        new OrderSubmitted(
                                "EVT-200", "ORD-200",
                                BigDecimal.ZERO,
                                "VND", null))));

        IngressOrder otherTenant = new IngressOrder(
                "ING-200-REV-2", "TENANT-B", "oms",
                new OrderSubmitted(
                        "EVT-200", "ORD-200",
                        new BigDecimal("10"),
                        "VND", null));

        assertThrows(SecurityException.class, () ->
                new ReplayReviewPolicy(validator)
                        .revalidate(originalCase, otherTenant, true));
    }
}
~~~

This test only verifies a **pure Java scope check**. Full security review must verify actor authentication, case ownership, payload provenance, action permissions, and server-side auditing.

## 16. Interactions with Enterprise Integration Patterns

### 16.1. Filter Before or After Transformer?

~~~text
Option A:
  Ingress -> Basic Filter -> Transformer -> Business Handler

Option B:
  Ingress -> Validation Transformer -> Filter -> Business Handler
                                         |
                                         +-> Quarantine
~~~

**Option B** works well when quarantine needs **reason codes** and policy versions. However, if malicious input could make the Transformer throw (e.g., payload deserialization), enforce **size limits, an error boundary before the Transformer**, or preliminary validation. Never catch every exception and treat it as business-invalid.

### 16.2. Router: Do Not Let Invalid Messages Leak to Business Channels

A system can use a Content-Based Router instead of a Filter:

~~~text
ValidationOutcome
   -> route(valid ? "orders.valid" : "orders.quarantine")
~~~

This is also valid. Filter + `discardChannel` highlights the **accept/reject** semantics of Message Filter, while a Router scales easily to multiple branches: `VALID`, `INVALID_SCHEMA`, `INVALID_BUSINESS`, `SECURITY_REJECTED`.

However, if a Router sets `defaultOutputChannel` to the business flow, a missing mapping could let invalid messages leak into the main branch. **Fail closed**: unknown routes should go to controlled quarantine/error flows.

### 16.3. Splitter: Each Invalid Part Needs Its Own Identity

~~~text
Batch B-1
  -> Splitter
      -> Item I-1 valid
      -> Item I-2 invalid
      -> Item I-3 valid
~~~

If a Filter only lets I-1 and I-3 pass, an **Aggregator** waiting for all three parts per `sequenceSize=3` can stall. Define:

1. Quarantine for **item I-2** carrying `batchProcessingId + itemId` or a stable child key.
2. A **failure outcome/placeholder** emitted to the Aggregator if the business contract expects an outcome per item.
3. A release strategy based on the **set of child IDs**, not merely message count.
4. Timeouts and partial/final failure policies for the batch.

**Never count message I-1 twice in place of I-2.** Nor does a child's quarantine ID replace the batch correlation ID.

### 16.4. Aggregator: Quarantine Is Not Automatically a Reply

Sending an event to quarantine signals a need for investigation; it does not give the Aggregator a **valid business result**. When downstream needs a final verdict, design:

~~~text
Item I-1 -> Outcome(SUCCESS)
Item I-2 -> Outcome(INVALID, reasonCode=...)
Item I-3 -> Outcome(SUCCESS)
   -> Aggregator -> BatchResult(PARTIAL_FAILURE)
~~~

This is an application contract. Never fabricate a `SUCCESS` for I-2 just to complete the sequence; if a rejection outcome is emitted, it must carry the accurate reason.

### 16.5. Scatter–Gather: One Invalid Branch Affects the Final Decision

~~~text
REQ-1
  -> Inventory check: PASS
  -> Fraud request invalid: QUARANTINED
~~~

If Fraud is mandatory, Gatherer **must not confirm the order** solely because Inventory passed. Emit an outcome/timeout for the Fraud branch per business contract, and use idempotency/correlation so replies from other requests or late replays never mix.

### 16.6. Resequencer: Invalid Items Create Gaps

Suppose a sequence `1,2,3`:

~~~text
seq=1 valid
seq=2 invalid -> quarantine
seq=3 valid
~~~

A Resequencer downstream of the Filter can wait for `#2` forever if the contract requires a complete sequence. Handle this with a **placeholder outcome** carrying `sequenceNumber=2` and reason code, or quarantine the whole group, or release under an approved gap policy. Never arbitrarily **increment `sequenceNumber`** on other messages to hide the missing item.

### 16.7. Idempotent Receiver: Invalid Duplicates Still Need Auditing

An invalid event may be redelivered multiple times by the broker. The quarantine writer should deduplicate on a stable identity, yet the **idempotency key used to create a quarantine case** is not necessarily the **business operation ID** used once an authorized replay becomes valid.

~~~text
quarantineKey = tenant + source + originalEventIdentity
businessOperationKey = tenant + businessOperationType + operationId
~~~

Sharing one key with ambiguous semantics can cause:

- Marking invalid as `SEEN`, wrongly blocking a later valid replay.
- Replaying with a new envelope ID bypassing business idempotency and creating duplicate side effects.
- Two independent consumer branches sharing a key, causing the second branch to falsely treat it as a duplicate.

### 16.8. Claim Check: Quarantining a Token Differs from Quarantining Payload

If a message carries only a **claim check ID** referencing the payload, putting that token in quarantine while the **data in the Claim Store expires or gets deleted** makes replay impossible.

When designing:

- Align claim TTL with the quarantine review/replay horizon.
- Retain a protected snapshot/reference if security policy permits.
- Record `CLAIM_EXPIRED`/`CLAIM_MISSING` rather than fabricating a fake business-invalid failure.
- Never issue new claim IDs to bypass revocation/authorization.

### 16.9. Gateway and Synchronous Requests

If a Gateway expects a reply, a Filter discarding the message into quarantine can make the caller **wait until timeout** because no reply travels back on the old path.

Define an explicit contract:

~~~text
Request valid   -> ACCEPTED / business result
Request invalid -> REJECTED_VALIDATION (issues, quarantineRef)
Request pending -> PENDING (operationId)
Technical error -> RETRYABLE_ERROR / INTERNAL_ERROR per policy
~~~

**Do not assume `discardChannel` automatically sends a reply to a Gateway.** When a synchronous outcome is required, design and test an explicit reply path/gateway output; a Router/handler returning `ValidationResponse` often works better than a one-way quarantine writer.

## 17. Error Channel, Retry, and Quarantine: Avoiding Infinite Loops

### 17.1. Validation Errors and Validator Errors Are Two Different Things

~~~text
Case A:
  validator.validate(order) returns issues=[AMOUNT_MUST_BE_POSITIVE]
  -> Normal invalid route -> Quarantine

Case B:
  validator.validate(order) throws due to unhandled bug
  -> Technical error, needs error handling

Case C:
  validator returns invalid, quarantine DB unavailable
  -> Persistence failure, case not durably stored
~~~

**Do not lump Cases B/C into `INVALID_BUSINESS`.** A validator can crash from a bug, null pointer, or unreachable reference data. Quarantining all of them as bad input wrongly blames producers and hides system incidents.

### 17.2. Retry Policy by Failure Class

| Error | Auto-retry same payload? | Why? |
|---|---|---|
| Missing `orderId` | Useless if input is immutable. | Needs producer fix or authorized replay. |
| Negative amount | Useless. | Deterministic rule failure. |
| Unsupported schema version | Not until parser/schema is compatible. | Immediate retry just repeats the failure. |
| Quarantine DB temporarily down | Bounded retry. | Data can persist once the store recovers. |
| Broker publish/ack timeout | Possibly, per delivery semantics. | May already be published; needs stable identity/dedupe. |
| Validator code bug | Do not replay infinitely. | Requires code fix/deploy and controlled revalidation. |
| Unknown tenant/security denied | Not with the same credentials. | Avoids retrying attacks. |
| Business handler timeout after valid | Retry/reconcile the operation. | Do not file into business-invalid quarantine. |
| Same quarantine key, payload conflict | Quarantine conflict/manual review. | Never silently overwrite. |

### 17.3. Never Route an Error Flow Back Into the Filter Infinitely

~~~mermaid
flowchart TD
    V["Validation Endpoint"] -->|invalid| Q["Quarantine Writer"]
    Q -->|DB failure| ER["Error Recovery"]
    ER -->|bounded retry| Q
    ER -->|retry exhausted| ALT["Fallback durable route / alert"]
    ALT --> MAN["Manual recovery"]
~~~

An anti-pattern:

~~~text
Validation -> Quarantine -> DB exception
  -> errorChannel -> Validation -> Quarantine -> DB exception -> ...
~~~

If the error handler has no retry limit or classification, the same invalid event can spin forever, exhausting resources and flooding logs. Enforce max attempts, backoff, dead-letter/fallbacks, or pause intake per policy.

### 17.4. If the Business Handler Fails After Validation Passes

Do not reroute it labeled `VALIDATION_FAILED` just because the handler threw. Data that passed validation can still encounter:

- Dependency timeouts.
- Database concurrency conflicts.
- Stale state or optimistic locking failures.
- Business outcomes like unavailable inventory.
- Payment already completed and duplicate redeliveries.

These require dedicated **error handling/retry/idempotency**. Quarantine can hold a "processing failure" case if desired, provided its **kind** is distinct from "invalid input".

### 17.5. Poison Messages and Error Sources

A raw record causing the deserializer to throw immediately may need a DLQ or raw quarantine. A typed message with deterministic bad fields belongs in business quarantine. A valid message that repeatedly crashes downstream services may need a technical DLQ after retries. **Do not apply one blanket formula of retrying N times then dumping everything into the same queue without reason or ownership.**

## 18. Observability: Distinguishing Received, Rejected, and Persisted

### 18.1. Milestone Structured Logs

~~~text
event=INGRESS_RECEIVED
  envelopeRef=ING-100
  source=oms
  traceRef=...

event=VALIDATION_COMPLETED
  envelopeRef=ING-100
  policyVersion=orders-v1
  outcome=INVALID
  reasonCodes=[AMOUNT_MUST_BE_POSITIVE]

event=QUARANTINE_WRITE_REQUESTED
  envelopeRef=ING-100

event=QUARANTINE_PERSISTED
  quarantineRef=Q-100
  source=oms
  status=NEW

event=INGRESS_ACKNOWLEDGED
  envelopeRef=ING-100

event=REPLAY_APPROVED
  quarantineRef=Q-100
  correctionRevision=REV-2
  actorRef=...

event=REVALIDATION_COMPLETED
  quarantineRef=Q-100
  outcome=VALID
~~~

This is a **proposed application log schema**, not default events emitted by Spring Integration. Log `QUARANTINE_PERSISTED` only after receiving storage commit confirmation per contract; `MessageChannel.send()` is not necessarily proof of durable persistence.

### 18.2. Separate Metrics by Milestone

| Suggested metric | Purpose |
|---|---|
| `validation_messages_received_total` | How many deliveries entered the validation flow? |
| `validation_passed_total` | How many messages passed the policy? |
| `validation_rejected_total{reason,policy}` | How many invalid by reason/version? |
| `quarantine_persisted_total{kind}` | How many cases were durably persisted? |
| `quarantine_duplicate_total` | How many redeliveries were deduplicated? |
| `quarantine_conflict_total` | Reused identity with conflicting payload? |
| `quarantine_write_failed_total{reason}` | Store failures. |
| `quarantine_cases_open` | Backlog of NEW/UNDER_REVIEW cases. |
| `quarantine_case_age_seconds` | Which cases have been sitting too long? |
| `quarantine_replay_attempt_total{result}` | Revalidate/replay successes vs failures? |
| `quarantine_replay_loop_prevented_total` | Blocked replays lacking corrections? |
| `validation_deserialization_failed_total` | Decode failures before typed Filter. |
| `quarantine_raw_bytes_total` | Volume of stored raw payloads. |
| `quarantine_cleanup_failed_total` | Retention cleanup failures. |
| `validation_filter_latency_seconds` | Validation/filter latency. |

These names are **measurement suggestions**. Spring Integration/Micrometer may expose their own meters depending on version and configuration; do not assume the framework emits all of these automatically.

**Avoid high-cardinality labels:** never use `quarantineId`, `eventId`, `orderId`, `traceId`, emails, or user IDs as metric labels. Keep them in access-controlled, retention-bounded logs, traces, and audits.

### 18.3. Numbers That Should Reconcile

A good dashboard helps answer:

~~~text
ingress received:        10,000 deliveries
passed validation:        9,700
rejected invalid:           300
quarantine persisted:       295
quarantine write failed:      5
~~~

The sample figures above reveal **5 invalid messages lacking proof of durable persistence**. If a metric only counts `validation_rejected_total=300` and reports "300 quarantined", that report is false. Track retries, persisted acknowledgments, and pending records too.

Totals do not have to match instantaneously in async flows because of in-flight messages and retries; use time windows, correlation, and states rather than raw instantaneous differences.

### 18.4. Useful Alerts

| Signal | Why it matters |
|---|---|
| Sudden spike in invalid rate by source/schema | Broken producer deploy or contract drift. |
| Rising quarantine persistence failures | Risk of losing or backing up invalid messages. |
| NEW cases exceeding review SLA | Data-owning team is falling behind. |
| Repeated invalid from the same policy | Correction/replay did not fix root cause or producer did not update. |
| Rising raw parse errors | Schema conversion/adapter config mismatch. |
| Unusual spike in replay approvals | Risk of abuse or misbehaving automation. |
| Overdue retention cleanup | Data exposure and storage risks. |
| Unknown tenant/security errors | Possible misconfiguration or attack. |

### 18.5. Message History Is Not Enough for Auditing

Spring Integration Message History, when enabled, helps trace messages across components. Yet it does not prove:

- That the quarantine case durably committed to the DB.
- That the payload was properly encrypted and access-controlled.
- Which authorized operator edited which case.
- Which policy version ran during revalidation and what the business outcome was.
- That a raw message failing decoding ever reached the Filter's discard channel.

Combine **integration logs, the case store, broker delivery state, tracing, and review/replay audit trails**.

## 19. Diagnosing When an Invalid Message "Disappears"

Suppose a producer claims it sent `EVT-300`, the business handler never processed it, and operations cannot find a quarantine case.

An investigation checklist:

1. **Source:** did the producer actually publish the record or only return a local enqueue result?
2. **Broker:** does the record still sit in a partition/queue? When did ack/offset commit happen?
3. **Deserialization:** could the inbound adapter read/parse the message? Did it fail before the typed Filter?
4. **Trusted context:** were security context, tenant, and source mappings valid, or was the message blocked before validation?
5. **Validator:** which policy version ran, and was the outcome valid, invalid, or an exception?
6. **Filter:** is `discardChannel` configured? Did `throwExceptionOnRejection` send the flow down a different error path?
7. **Discard handler:** does `orders.quarantine` have an active subscriber? Was the channel stopped?
8. **Store:** did the write succeed, or hit a DB timeout, unique conflict, or serialization error?
9. **Deduplication:** does the record already exist under another quarantine ID sharing the same stable ingress key?
10. **Retention:** was the record expired, cleaned, or archived? Check tombstones and audits.
11. **Replay:** was the case corrected/replayed and transitioned? Is there lineage?
12. **Authorization:** is the operator querying the right tenant/source with permission to view the case?
13. **Observability:** which logs confirm `VALIDATION_COMPLETED`, `QUARANTINE_PERSISTED`, and `INGRESS_ACKNOWLEDGED`?
14. **Regression:** write a test reproducing the exact drop point and fix the ack/error route.

### 19.1. Quick Diagnostics

| Symptom | Where to check first |
|---|---|
| No validator logs, yet conversion errors appear | Deserializer/inbound adapter error route. |
| Validation invalid logged, no discard handler logs | Filter `discardChannel`/subscriber/`throwExceptionOnRejection`. |
| Discard handler called, no case in store | DB write/transaction/unique conflict/TTL. |
| Case exists, yet operator cannot see it | Tenant scope, review UI query/authorization/retention. |
| Quarantine cases multiply after broker retries | Stable ingress identity and idempotent writes. |
| Replay still fails with identical error code | Correction was not applied or policy unchanged. |
| One quarantined item stalls the Aggregator | Missing child outcome/sequence/release strategy. |
| Gateway times out on invalid request | Discard path lacks a response contract. |
| Technical outage counted in invalid rate | Wrong error classification. |

### 19.2. Runbook When Quarantine Cannot Write

~~~text
Detect:
  quarantine_write_failed_total increases

Protect:
  stop silent acknowledgment of invalid inputs
  apply bounded retry/backpressure

Contain:
  send to approved durable fallback if available
  avoid logging raw sensitive payload

Recover:
  restore store / repair schema / free capacity
  redeliver with same stable ingress identity
  dedupe and reconcile completed writes

Verify:
  number of rejected vs durably stored cases
  failed messages no longer in-flight without ownership
~~~

**Never route all invalid messages to the business handler** just because the quarantine store is down. That is failing open and can cause corrupt business side effects.

## 20. Message Filter → Quarantine Test Matrix

| ID | Scenario | What to verify | Must not happen |
|---|---|---|---|
| QF-01 | Valid typed order | Enters business handler, no quarantine case. | Wrongly rejected. |
| QF-02 | Amount equals 0 | Quarantined with `AMOUNT_MUST_BE_POSITIVE`. | Calls business handler. |
| QF-03 | Negative amount | Quarantined with accurate reason. | Silent drop. |
| QF-04 | Null amount | Quarantined, validator does not throw NPE. | Ambiguous error. |
| QF-05 | Amount exceeds demo limit | `AMOUNT_EXCEEDS_LIMIT`. | Accepted outside policy. |
| QF-06 | Unsupported currency | `UNSUPPORTED_CURRENCY`. | Sent to payment. |
| QF-07 | Blank orderId | `ORDER_ID_REQUIRED`. | Quarantined without reason. |
| QF-08 | Blank eventId | `EVENT_ID_REQUIRED`, still has trusted envelope ID. | Unable to create quarantine case. |
| QF-09 | Multiple invalid fields at once | All checked issues recorded. | Reporting only first error when contract requires all. |
| QF-10 | Null order payload inside envelope | `ORDER_PAYLOAD_MISSING`. | Business handler receives null order. |
| QF-11 | Trusted source not in allowlist | `UNSUPPORTED_SOURCE`. | Bypassing source rule. |
| QF-12 | Invalid envelope metadata | Rejected at trusted ingress boundary. | Treating untrusted tenant as verified. |
| QF-13 | Wrong JSON amount type before deserialization | Adapter error route/raw quarantine. | Assuming typed Filter ran. |
| QF-14 | Undecodable malformed JSON | Raw reference + safe error code. | Logging full sensitive raw payload. |
| QF-15 | Adapter authorization denied | Security rejection/audit. | Persisting under wrong tenant scope. |
| QF-16 | Filter false, `discardChannel` configured properly | Quarantine handler receives `ValidationOutcome`. | Message silently lost. |
| QF-17 | Filter false with `throwExceptionOnRejection` enabled | Configured behavior verified. | Assuming normal discard flow runs anyway. |
| QF-18 | Discard channel has no subscriber | Error/handling per channel contract. | ACKing and losing message. |
| QF-19 | Quarantine store unavailable | Bounded retry/fallback/alert. | Faking persisted success. |
| QF-20 | DB persists case, broker ack lost | Redelivery deduplicates to same case. | Creating duplicate cases. |
| QF-21 | Two invalid deliveries with same envelope identity | One case stored or idempotent update. | Unbounded duplicate cases. |
| QF-22 | Same envelope identity, different payload | Conflict detected and evidence stored. | Silent overwrite. |
| QF-23 | Two tenants using same local envelope ID | Isolated by tenant scope. | Merging both cases. |
| QF-24 | Two source systems using same ID | Isolated by source scope. | Merging both cases. |
| QF-25 | In-memory quarantine store restart | Demo limitation documented. | Claiming durability. |
| QF-26 | Durable DB + restart | Case recovered/readable. | Losing cases on node death. |
| QF-27 | Object payload saved, metadata DB fails | Orphan cleanup/reconciliation. | Uncontrolled data leakage. |
| QF-28 | Metadata case saved, object missing | Detect inaccessible payload. | Replaying empty payload. |
| QF-29 | Oversized payload | Size cap/protected reference. | OOM/giant log dumps. |
| QF-30 | Quarantine record contains PII | Encryption/access/retention enforced. | Unauthorized operators reading raw data. |
| QF-31 | Replay without authorization | Denied/audited. | Pushing into business handler. |
| QF-32 | Correction from another tenant | Rejected for scope mismatch. | Cross-tenant replay. |
| QF-33 | Valid correction then revalidate | Passes versioned policy. | Calling handler before validation. |
| QF-34 | Replay with unfixed payload | Still invalid + bounded attempts. | Infinite loop. |
| QF-35 | Policy evolves from v1 to v2 | New outcome keeps audit/lineage. | Overwriting old reasons. |
| QF-36 | Replay for already-completed business operation | Idempotency returns stored result. | Duplicate side effects. |
| QF-37 | Filter drops Splitter child | Batch emits failure outcome or timeout. | Aggregator waits forever. |
| QF-38 | Resequencer awaits quarantined seq | Gap/placeholder/recovery defined. | Delivering out of order. |
| QF-39 | Scatter–Gather has an invalid branch | Does not emit final success missing a branch. | Confirming order prematurely. |
| QF-40 | Claim Check token expired during review | Protected replay source/expiry handling. | Guessing payload. |
| QF-41 | Invalid request via Gateway | Explicit response contract. | Caller waits forever due to discard. |
| QF-42 | Technical DB timeout after valid | Classified as technical failure. | Marking payload invalid. |
| QF-43 | Cleanup past retention deadline | Alerts/audit/cleanup retries. | Data retained indefinitely. |
| QF-44 | Duplicate yet valid message | Idempotent business handling. | Quarantining merely for redelivery. |
| QF-45 | Two operators replay concurrently | State CAS/fencing or workflow locking. | Two side effects. |
| QF-46 | Store overloaded/queue full | Backpressure and loss prevention. | Silent drop. |
| QF-47 | Error handler fails again | Bounded recovery/fallback. | Infinite recursive loop. |
| QF-48 | Rejected count differs from persisted count | Dashboard accurately shows pending/failed counts. | Claiming all saved before commit. |

### 20.1. What Each Test Level Proves

| Level | Should verify | Does not prove |
|---|---|---|
| **Unit validator** | Rules, issue codes, policy version, null safety. | Filter routed accurately. |
| **Spring Integration** | Transformer → Filter → discard channel → handler. | Persistence across restarts if using fake store. |
| **Database integration** | Unique keys, transactions, case identity, concurrent writes. | Broker ack semantics without a broker. |
| **Adapter integration** | Deserialization errors, header mapping, DLQ, retries, acks. | Business side effects if handler is mocked. |
| **Replay workflow** | Auth, revalidation, versioned corrections, auditing. | Payment idempotency without real provider/ledger. |
| **System/chaos test** | DB outages, process crashes, throughput, backpressure, retention. | Untested production scenarios outside test scope. |
| **Security test** | Cross-tenant access, PII redaction, replay permissions. | Full risk posture without trust-boundary review. |

**Passing validator unit tests does not prove invalid messages are safely quarantined.** You need at least one test traversing real channels/adapters and persistent quarantine writers at the production boundaries you rely on.

## 21. Common Mistakes

| Mistake | Consequence | Better approach |
|---|---|---|
| Calling `filter(...)` with no discard path. | Invalid messages vanish. | Configure discard channel/flow and assert persistence. |
| Using only a boolean without saving reason codes. | Cannot tell what to fix or trace policy. | `ValidationOutcome` with issues and version. |
| Re-running validator inside quarantine handler. | Outcomes diverge when policy/time/state changes. | Preserve the outcome computed at validation. |
| Lumping all exceptions into invalid. | Blames producers when DB/adapters fail. | Separate technical/business/security failures. |
| Assuming Filter catches malformed JSON. | Misses errors before deserialization. | Adapter error routes and raw quarantine. |
| Setting `throwExceptionOnRejection` while expecting normal discard. | Messages take a different error path. | Pick clear semantics and test exact config. |
| Naming a channel `quarantine` and assuming durability. | Cases lost on restart. | Persistent store/queue and ack policy. |
| ACKing broker before case commits. | Record missing from both branches. | Persist then ack per delivery contract. |
| Treating `send=true` as durable persistence. | Tracks wrong milestone. | Verify DB commit or durable enqueue. |
| Deduplicating on newly generated Spring message IDs. | Redeliveries create duplicate cases. | Stable trusted ingress identity. |
| Treating different payloads with same ID as duplicates. | Loses evidence and corrupts data. | Conflict detection + audit. |
| Taking tenant ID straight from invalid payloads. | Misfiles under wrong tenant / leaks data. | Trusted identity from authentication context. |
| Logging raw payloads and exception messages. | Leaks PII/secrets. | Protected store + redacted metadata. |
| Replaying by invoking business handlers directly. | Bypasses validation and permissions. | Correction → auth → revalidation → dispatch. |
| Generating a fresh `operationId` on every replay. | Defeats idempotency. | Preserve stable business operation identity. |
| Revalidation overwriting old issues/history. | Loses original rule evidence. | Versioned attempts/audits. |
| Auto-replaying deterministic invalid data forever. | Poison loops/queue saturation. | Bounded retries; require fixes or policy updates. |
| Filtering a child without notifying the Aggregator. | Message group waits forever. | Failure outcome/placeholder and timeouts. |
| Discarding Gateway requests without replying. | Caller hits confusing timeouts. | Explicit response contract for invalid inputs. |
| Counting rejected as persisted. | Misreports message loss. | Separate received/invalid/persisted/acked metrics. |
| Keeping only expiring Claim Check tokens. | Cannot replay the original. | Protected replay source and aligned TTLs. |
| Cleanup deleting all evidence before replay horizon. | Late retries lack lineage/dedupe. | Tombstones/aligned retention. |
| Allowing arbitrary operators to replay cross-tenant. | Unauthorized data exposure or mutation. | Principal-bound authorization/audit. |
| Putting `quarantineId` in Prometheus metric labels. | High cardinality hurts monitoring. | Finite code/outcome/policy labels; IDs in logs/audits. |

## 22. Practice Exercises

1. **Basics:** use `OrderValidationPolicy` to return `ValidationOutcome` for an order with a negative amount and invalid currency. Verify both reason codes.
2. **Valid route:** configure `validateAndRouteOrders` and verify valid inputs only reach `orders.valid`.
3. **Invalid route:** send amount 0; verify `InMemoryQuarantineStore` holds one case and `AcceptedOrderProbe` receives nothing.
4. **Missing discard config:** temporarily omit `discardChannel` in tests, observe invalid messages produce no case; explain why that fails requirements.
5. **Throw vs discard:** enable `throwExceptionOnRejection`, compare the exception/error path against `discardChannel`.
6. **Multiple validation issues:** send an order missing `eventId`/`orderId` with negative amount; assert all expected error codes.
7. **Malformed JSON:** use a real inbound adapter to send raw wrongly typed records; verify errors occur at the deserializer without reaching the typed Filter.
8. **Raw quarantine:** design a raw-error record carrying source, transport reference, safe error code, and protected payload reference.
9. **Policy version:** add `orders-v2` allowing a new currency; store revalidation outcomes without overwriting v1 history.
10. **Duplicate redelivery:** resend the same `IngressOrder.envelopeId` twice; verify only one quarantine case exists.
11. **Identity conflict:** reuse an envelope ID with a different payload; verify conflict detection prevents silent overwrites.
12. **Tenant scope:** send the same `envelopeId` across two tenants; verify two isolated cases are created with separate read permissions.
13. **Source scope:** have two producers use the same local event ID; verify quarantine keys do not collide.
14. **Persistent store:** replace the fake map with a JDBC repository using unique constraints; test two transactions storing the same case.
15. **Ack window:** simulate a successful DB commit followed by a lost broker ack; redelivery must deduplicate without losing the case.
16. **Quarantine DB unavailable:** make writes throw; verify consumers do not report persisted and apply bounded retries/error handling.
17. **Capacity:** cap pending cases and payload sizes; verify overload does not silently drop messages.
18. **Correction:** fix the amount in an approved revision and call `ReplayReviewPolicy.revalidate`; verify it passes without automatically calling the business handler.
19. **Authorization:** attempt to replay tenant A's case under tenant B's principal; verify denial and auditing.
20. **Replay loop:** resend the unfixed invalid original three times; design a `STILL_INVALID` state and attempt limits.
21. **Gateway:** build a `ValidationResponse` contract for invalid inputs, ensuring callers never time out waiting on Filter discards.
22. **Splitter/Aggregator:** a batch has invalid child I-2; emit a rejection outcome instead of leaving the Aggregator stuck forever.
23. **Resequencer:** make sequence #2 invalid; verify gap handling and placeholder/recovery per contract without releasing #3 early.
24. **Scatter–Gather:** Fraud request is invalid; verify the overall outcome is not `CONFIRMED` just because Inventory passed.
25. **Claim Check:** a token stays quarantined past claim TTL; design a protected replay source and test expired claims.
26. **Metrics:** count received, invalid, persisted, failed, and deduped as distinct milestones; do not attach `eventId` as a metric label.
27. **Security:** mask `customerEmail` in logs and restrict original payload reads by tenant/operator roles.
28. **Retention:** purge processed cases per policy while keeping minimal metadata to prevent duplicate replays where permitted.
29. **System test:** restart the consumer between validation and quarantine write, then between quarantine commit and ack; verify proper recovery.
30. **Runbook:** write a checklist for when invalid messages lack cases, covering adapter to `discardChannel`, DB, retention, and review permissions.

### Completion Criteria

An implementation meets the goals when:

- Invalid typed messages **never** reach business handlers, yet have a **clear isolation and traceability path**.
- Reason codes and policy versions are persisted in outcomes/cases, not just booleans.
- Malformed raw data has a dedicated adapter error route instead of wrongly assuming the Filter handled it.
- Quarantine persistence and ingress ack ordering/delivery semantics are tested.
- Redeliveries sharing a trusted event identity do not duplicate cases; conflicting payloads never silently overwrite.
- Replays enforce authorization, versioned corrections, revalidation, auditing, idempotency, and attempt limits.
- Data minimization, retention, encryption, tenant isolation, and safe logging are defined.
- Unit, integration, and adapter tests verify every critical trust boundary.

## 23. Self-Check Questions

**Q1:** A Message Filter returns false without a discard channel. What can happen?

The message is removed from the business flow without a quarantine record. If the system requires saving invalid inputs, this is a design flaw requiring a configured discard route and tests.

**Q2:** How does quarantine differ from a DLQ?

Quarantine is a **workflow for isolation, classification, investigation, and policy-driven replay**. A DLQ is typically a holding destination after processing/transport failures; a DLQ can serve as quarantine storage if it includes sufficient metadata, permissions, retention, and workflow tooling.

**Q3:** Wrong JSON types prevent the inbound adapter from deserializing. Does the Filter receive a typed `OrderSubmitted`?

**No.** The failure occurs before the Filter. Error handling at the adapter/deserializer or a raw-error route is needed.

**Q4:** Should invalid messages always throw exceptions?

**Not necessarily.** Business validation returning false can be a normal routing outcome: construct an outcome with issues and route it via `discardChannel`. Technical failures are a separate matter.

**Q5:** Why is storing only a valid/invalid boolean insufficient?

You lack reason codes, field paths, and policy versions for root-cause tracing, fixing, or controlled revalidation.

**Q6:** Does `MessageChannel.send()` returning true prove quarantine persisted durably?

**Not by default.** The channel may only have accepted/dispatched the message. Rely on commit/ack semantics of the store or durable queue.

**Q7:** The broker delivered the same invalid message twice. Should two quarantine cases be created?

Usually not if it is the **same logical input**: use a stable ingress identity to deduplicate. Still, detect conflicts if the same key carries a different payload.

**Q8:** Should the same `eventId` across two different tenants share one quarantine case?

**No.** Quarantine keys must be scoped by trusted tenant/source/identity and checked for permissions.

**Q9:** Can `tenantId` inside invalid JSON be trusted as the scope?

**No.** Tenant must come from authentication/trusted ingress context and be cross-checked against the payload if needed.

**Q10:** The quarantine DB write fails, yet the consumer still acks the broker. What is the risk?

The message can vanish from both business processing and quarantine. Apply controlled retry/backpressure/fallbacks and ack only after durable handoff.

**Q11:** During replay, can you invoke the business handler directly to skip validation?

Not as the default workflow. You must review, authenticate/authorize, fix data or versioned policy, revalidate, and dispatch with auditing and idempotency.

**Q12:** If an invalid message is replayed unchanged, do infinite retries help?

Usually not for deterministic errors. Corrections or approved rule changes are needed; infinite retries just create poison loops.

**Q13:** A new policy accepts an old quarantined input; can the old reason history be deleted?

It should not be. Retain the old policy version and outcome; record a new revalidation attempt with lineage.

**Q14:** A Filter drops Splitter child #2 while Aggregator waits for three. What is the risk?

The Aggregator may wait forever. Use a rejection outcome/placeholder or explicit release/timeout policy, never treating a dropped child as succeeded.

**Q15:** Resequencer receives #1 and #3 while #2 is quarantined. Can #3 be released before #2?

Not if the ordering contract requires full sequences. Use gap/placeholder/recovery handling or an approved partial-release policy.

**Q16:** A Gateway request is discarded by a Filter. Is the caller guaranteed to receive a rejected result?

No. A discard channel does not automatically send a reply back to a Gateway; an explicit response/error contract is needed to avoid timeouts.

**Q17:** Quarantine only saved a claim ID, and during review the claim expired. Can the original be recovered automatically?

No. You need a valid protected replay source or an unrecoverable state; never guess the payload.

**Q18:** An invalid message hits a technical store error. Should it be marked business-valid to clear the backlog?

**No.** That is a dangerous fail-open. Handle store errors with appropriate retries, fallbacks, or pausing intake—never alter validation outcomes.

**Q19:** Why avoid putting `quarantineId` in Prometheus metric labels?

It is a very high-cardinality value that inflates monitoring cost and load. Use finite outcome/reason/policy labels, keeping specific IDs in logs and audits.

**Q20:** Does a quarantined message mean business processing is complete?

No. Quarantine only confirms an isolation/intake outcome per contract. Revalidation, business acceptance, and business completion are separate milestones.

## 24. Conclusion

**Routing invalid messages to quarantine** protects business flows while preserving **observability, investigation, and data recovery**. With Spring Integration, a clear model is **Validation Transformer creating `ValidationOutcome` → Message Filter evaluating valid/invalid → `discardChannel` routing invalid cases to a Quarantine Handler**. Messages failing deserialization need an **adapter-level error path**, because the typed Filter is never invoked.

A trustworthy system does not stop at `filter(false)` or a channel named "quarantine". It requires reason codes, policy versions, trusted source/tenant metadata, durable storage, idempotent writes, ordered ack/retry handling, TTL/security controls, and controlled replay. Invalid inputs **differ** from transient technical failures, business rejections, and duplicate redeliveries; each category has clear handling and ownership.

In `SPRING_INTEGRATION_PATTERN`, test across layers: **validator unit tests → Spring Integration Filter/discard integration tests → adapter/deserializer error tests → durable store/ack/replay system tests**. When combining Router, Transformer, Splitter, Aggregator, Scatter–Gather, Resequencer, Claim Check, Gateway, retry, and error channels, always be able to answer three questions: **"Why was the message rejected?", "Where was it safely kept?", and "Who is authorized to fix it and return it to processing, and how?"**

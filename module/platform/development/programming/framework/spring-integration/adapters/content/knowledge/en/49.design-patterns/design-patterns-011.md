# Anti-Corruption Layer at System Boundaries with Spring Integration Adapters

When integrating two systems, the hardest part is not always opening an HTTP connection, fetching files over SFTP, or publishing to Kafka. The difficulty often lies in **both sides using different business concepts**. A partner system calls an order a `booking`, uses status codes `S1`/`S2`, and expresses amounts in minor currency units; the internal system uses `Order`, `OrderStatus`, and `Money` with explicit currency units. Letting partner concepts flow straight into the internal domain causes the entire codebase to gradually couple to an external system's vocabulary, states, error codes, and versioning quirks.

An **Anti-corruption layer (ACL)** is a Domain-Driven Design (DDD) pattern intended to **prevent an external bounded context's model from distorting an internal bounded context's model**. The ACL receives data/intent from external systems, **interprets its meaning**, translates it into the internal domain language, and translates results back when needed. It also decides how to react to invalid contracts, missing identifiers, differences in states, timestamps, units, errors, and version changes.

This lesson belongs to the **Design patterns** chapter of module `SPRING_INTEGRATION_ADAPTERS`. The module focuses on connecting external systems via **inbound/outbound adapters, gateways, pollers, and `MessageChannel`**, covering File, SFTP, HTTP, JMS, AMQP, Kafka, and databases. Within that architecture, Spring Integration provides **message transport and orchestration mechanisms**; the ACL provides the **semantic boundary** so protocol or partner-schema changes do not leak deep into the domain.

> **Core thesis:** An adapter knows **how** to exchange data with a partner; an ACL knows **what that data means** to the internal domain and how to express the domain in the partner's language. You can deploy them in the same flow, yet never conflate their responsibilities.

## 1. Learning Objectives

After this lesson, you can:

1. Explain the **Anti-corruption layer** in DDD and why it is valuable at integration boundaries.
2. Distinguish **transport adapter**, **gateway**, **DTO mapper**, **translator**, **facade**, **domain service**, and **ACL**.
3. Spot mismatches in **domain language, identifiers, states, timestamps, units, errors, security, and versions**.
4. Design **inbound** and **outbound** ACLs for systems with multiple partners and multiple protocols.
5. Build mapping rules that are **explicit, testable, and never silently drop data**.
6. Use Spring Integration Java DSL to structure **receive → validate → translate → domain channel** and **domain request → translate → outbound gateway → translate reply**.
7. Scope **canonical internal models** appropriately without creating a rigid “company-wide single model.”
8. Handle **contract evolution**, backward compatibility, unknown enums, partner reference mapping, and version drift.
9. Combine ACLs with **retries, idempotency, error channels, quarantine, auditing, tracing, trust boundaries, and transactions**.
10. Test ACLs across unit, contract, flow, transport, and end-to-end tests, understanding the proof limits of each layer.

## 2. The Problem: When an External Model Leaks Into the Domain

Suppose a delivery partner system emits an event:

~~~json
{
  "event_key": "evt-4280",
  "booking_ref": "SHIP-2026-000428",
  "phase": "S2",
  "event_time": "2026-11-23T16:00:00+07:00",
  "client_code": "customer-vn",
  "note": "delivered"
}
~~~

Internally, we want to persist a business event with clear semantics:

~~~json
{
  "eventId": "evt-4280",
  "shipmentId": "shp-2048",
  "status": "DELIVERED",
  "occurredAt": "2026-11-23T09:00:00Z",
  "tenantId": "VN"
}
~~~

These two representations differ **in far more than field names**:

| Partner attribute | Semantics to verify | Internal representation |
|---|---|---|
| `event_key` | Is the event ID stable across retries? Within what scope is it unique? | `eventId` scoped by source/tenant. |
| `booking_ref` | Partner-issued reference; can it be reused? | `shipmentId` via a trusted reference mapping table. |
| `phase = "S2"` | Does S2 mean “delivered,” “out for delivery,” or “accepted”? | Enum `DeliveryStatus.DELIVERED` once confirmed by contract. |
| `event_time` | Event occurrence time or send time? Valid offset? | `Instant occurredAt`. |
| `client_code` | Self-declared value or bound by source identity? | `tenantId` verified against trusted integration context. |
| `note` | Unstructured descriptive text; should it be stored/audited? | Ignore or store in approved metadata; never treat as status. |

If business code writes directly:

~~~java
if ("S2".equals(partnerEvent.phase())) {
    order.markDelivered();
}
~~~

then the domain now knows the partner's `S2` code. When the partner switches to `DEL`, every place referencing “S2” breaks. Worse: if the partner changes the **meaning** of `S2` while keeping its name, the code keeps running and corrupts business state.

**An ACL solves this by centralizing contract interpretation at the boundary**, passing into the domain only verified objects and actions expressed in internal vocabulary.

## 3. Anti-Corruption Layer Architecture Diagram

~~~mermaid
flowchart LR
    subgraph EXTERNAL["Partner bounded context"]
        EXT["External API / File / Topic / DB"]
        EDTO["External DTO + partner semantics"]
    end
    subgraph BOUNDARY["Integration boundary"]
        ADAPTER["Spring Integration adapter / gateway"]
        VALID["Transport/contract validation"]
        ACL["Anti-corruption layer<br/>Translate + Interpret + Policy"]
    end
    subgraph DOMAIN["Internal bounded context"]
        CMD["Internal command / event / value objects"]
        SERVICE["Domain service / application service"]
        MODEL["Domain model"]
    end
    EXT --> EDTO --> ADAPTER --> VALID --> ACL --> CMD --> SERVICE --> MODEL
    MODEL -. "Domain result" .-> ACL
    ACL -. "External response" .-> ADAPTER
~~~

**Two distinct boundaries:**

1. **Transport boundary:** bytes/records/HTTP requests/broker deliveries are turned into messages with payloads and headers.
2. **Semantic boundary:** external contracts are interpreted into domain commands/events/value objects with verified invariants and explicit mappings.

An ACL is not always **a single class**. It can be a cohesive package/module of translators, identifier resolvers, semantic validators, exception mappers, and application-facing facades with unified tests and ownership.

## 4. How ACL Differs from Easily Confused Patterns/Components

| Component/pattern | Primary role | Is it an ACL? |
|---|---|---|
| **HTTP/SFTP/JMS/AMQP/Kafka adapter** | Connects and transports data per protocol. | **Not automatically**. May only move bytes. |
| **Inbound/outbound gateway** | Request–reply and message-flow bridge. | Can sit along the path through an ACL. |
| **DTO mapper** | Reshapes field structures/types. | Part of an ACL when protecting semantic boundaries. |
| **Translator** | Converts language/models between two contexts. | Core building block of an ACL. |
| **Facade** | Provides a simplified API for a subsystem. | Can wrap an ACL, does not replace translation. |
| **Adapter pattern (GoF)** | Adapts interfaces for compatibility. | Can serve an ACL; insufficient alone against semantic leakage. |
| **Application service** | Orchestrates internal use cases. | Consumes ACL output; should never know external status codes. |
| **Domain service** | Enforces internal domain rules. | Must not depend on partner codes. |
| **Backend-for-Frontend (BFF)** | Tailors APIs for specific clients/UIs. | May use translators; different purpose from an ACL. |
| **Canonical data model** | Shared internal representation within a chosen scope. | Helpful, yet not an ACL without boundary translation/protection. |
| **Schema registry** | Tracks schemas and compatibility. | Aids contract governance; does not understand business meaning. |

A class that merely converts `snake_case` to `camelCase` is not a meaningful ACL. Conversely, if it **isolates external meanings, aligns domain invariants, blocks uninterpretable data, and prevents partner codes from leaking**, it fulfills the true role of an ACL even if named `PartnerTranslator`.

## 5. When to Invest in an ACL vs. Keeping It Minimal

**Invest in an explicit ACL when:**

- Both sides have **different business models**, even if both use Java/JSON.
- Partners evolve schemas/versions on independent schedules.
- External status and error codes do not map 1:1 to your domain.
- You must translate external IDs to internal IDs, money/time/units, or tenants.
- Integrating multiple partners for one use case, each with its own contract.
- Core domain must stay resilient when swapping HTTP for SFTP/Kafka or switching providers.
- High risk from malformed messages, duplicates, stale events, or unauthorized data.

**No need for a heavy ACL framework when:** the system is small, both sides genuinely share one bounded context, contracts are stable, and translation is trivial. A small tested translator suffices. Never pile on abstractions just for the DDD label.

### Signs an ACL is missing

- Service/domain code imports `com.partner.vendor.dto.*`.
- Internal enums contain `S1`, `S2` solely because an external party uses them.
- Each use case writes `if (status.equals("DEL"))` with diverging interpretations.
- An external field is assumed to be an internal ID without a mapping policy.
- HTTP errors or broker metadata leak into domain logic.
- Switching partners requires modifying multiple aggregates instead of one adapter/translator module.

## 6. ACL Design Principles

1. **Clear boundaries:** domain code never depends on vendor DTOs, protocol headers, or vendor exceptions.
2. **Semantics before syntax:** understand what `S2` means before renaming it to `DELIVERED`.
3. **Explicit mappings:** never default unknown enums to valid states.
4. **Never guess internal IDs from strings:** use authoritative reference mappings.
5. **Layered trust:** verify source authenticity/tenant at the boundary; treat payloads as untrusted data.
6. **Pure transformations where possible:** keep translators side-effect-free for easy unit testing and replay.
7. **Do not mix transport retries with business mapping:** transient errors must not masquerade as validation failures.
8. **Observable:** record correlation, contract version, mapping outcome, and quarantine reasons.
9. **Version change policy:** vendor updates must never silently alter domain behavior.
10. **Fail closed on critical ambiguity:** never invent statuses, currencies, or tenants when unverified.
11. **Owned and tested:** integration teams own contracts; domain owners approve business interpretations.

## 7. Layering a Pragmatic ACL

~~~text
integration/
  partner_acme/
    inbound/
      PartnerEventDto.java
      PartnerInboundFlow.java
      PartnerPayloadValidator.java
    outbound/
      PartnerReserveRequest.java
      PartnerReserveResponse.java
      PartnerOutboundFlow.java
    acl/
      PartnerEventTranslator.java
      PartnerResponseTranslator.java
      PartnerIdentityResolver.java
      PartnerErrorTranslator.java
      PartnerContractVersionPolicy.java
    tests/
      ... (located under matching src/test/java)
domain/
  shipment/
    DeliveryStatus.java
    DeliveryUpdate.java
    ShipmentApplicationService.java
~~~

This is an **illustrative layout**, not a mandatory Spring Integration structure.

| Layer | Input | Output | Responsibility |
|---|---|---|---|
| **Transport adapter** | HTTP/file/broker/DB | `Message<ExternalPayload>` or bytes | Connectivity, I/O, basic serialization, lifecycle. |
| **Contract validator** | External DTO + trusted metadata | Valid external contract or error | Schemas, required fields, versions, sizes, basic formats. |
| **Identifier resolver** | `partnerId + externalRef` | Internal entity ID or unresolved | Scoped reference mapping. |
| **Semantic translator** | Valid external data + reference | Internal command/event | Enums, units, timestamps, meanings, valid states. |
| **Domain application service** | Internal command | Domain result | Invariants and use-case authorization. |
| **Outbound translator** | Internal request/result | Partner request/response DTO | External contract formatting. |
| **Error translator** | Technical/contract/domain outcomes | Contract-compliant errors/responses | Prevents vendor exceptions leaking into core. |
| **Quarantine/reconciliation** | Unprocessable events | Evidence + recovery cases | Avoids dropping records or false successes. |

**Note:** An ACL must not **re-implement every domain rule**. It guards the boundary while application/domain services still enforce invariants. If an ACL maintains complex aggregate state itself, it becomes a second domain that drifts out of sync.

## 8. Bidirectional Translation: Inbound and Outbound

### 8.1. Inbound

~~~mermaid
flowchart LR
    RAW["External event<br/>PartnerDeliveryEventV1"] --> VALID["Contract validation"]
    VALID --> RESOLVE["Resolve partner reference<br/>+ trusted tenant"]
    RESOLVE --> TRANSLATE["Semantic translation"]
    TRANSLATE --> INTERNAL["DeliveryUpdate<br/>internal model"]
    INTERNAL --> DOM["Domain application service"]
    VALID -. "Reject" .-> QUAR["Quarantine + evidence"]
    RESOLVE -. "Unresolved" .-> QUAR
    TRANSLATE -. "Unknown semantics" .-> QUAR
~~~

An inbound flow may **validly fail** when it cannot map `phase = "S9"`. Routing that message to quarantine with reason `UNKNOWN_PARTNER_STATUS` is far safer than assuming `S9` means `DELIVERED` or silently ignoring it.

### 8.2. Outbound

~~~mermaid
flowchart LR
    CMD["ReserveShipmentCommand<br/>internal"] --> MAP["Outbound translator"]
    MAP --> REQUEST["PartnerReserveRequestV2"]
    REQUEST --> ADAPTER["HTTP/JMS/AMQP outbound gateway"]
    ADAPTER --> RESP["PartnerReserveResponseV2"]
    RESP --> BACK["Inbound response translator"]
    BACK --> RESULT["ReservationResult<br/>internal"]
    ADAPTER -. "Protocol error" .-> ERROR["Technical failure mapping"]
~~~

An outbound translator does more than rename fields. It **translates requests** into actions the partner understands, picks remote resource identifiers, formats timestamps/units/types, and translates replies/errors back into **a stable contract for the application service**.

## 9. Model Design: External DTOs Must Never Become Domain Entities

Suppose the internal system needs shipment progress update events. Using Java 17+ records to draw the boundary:

~~~java
package example.partner.external;

// Contract from a specific partner; never place inside the domain package.
public record PartnerDeliveryEventV1(
        String eventKey,
        String bookingRef,
        String phase,
        String eventTime,
        String clientCode) {
}
~~~

~~~java
package example.domain.delivery;

import java.time.Instant;

public enum DeliveryStatus {
    IN_TRANSIT, DELIVERED, RETURNED
}

public record DeliveryUpdate(
        String eventId,
        String shipmentId,
        DeliveryStatus status,
        Instant occurredAt,
        String tenantId) {
}
~~~

**Example assumption:** the external DTO was decoded from JSON or parsed from a file into a Java record; the real wire format may use `snake_case` while Java uses camelCase. Jackson/serializer field mappings must be configured on the adapter or DTO (e.g., `@JsonProperty`); **never assume Jackson automatically converts every name** without a naming strategy configured.

### 9.1. Both sides can rename independently

Partner renames `booking_ref` to `shipment_reference` in v2: update partner DTO/translator v2, **leaving domain `DeliveryUpdate.shipmentId` untouched** when internal meaning stays identical.

Domain evolves status from an enum to a value object with a reason: update the ACL/domain interface in a controlled migration without forcing partners to change wire contracts immediately.

## 10. Translator Pattern: Explicit and Easily Testable

Separate **pure rules** (status/time/required fields) from **external reference lookups** involving I/O. That keeps mapping unit tests fast while resolver tests separately verify idempotency/caching and bad data.

### 10.1. Boundary-verified trusted context

~~~java
package example.partner.acl;

public record TrustedPartnerContext(
        String partnerId,
        String tenantId,
        String authenticatedClientCode) {
}
~~~

Construct this object solely from **authentication outcomes, approved connection/source configurations, or inbound adapter mappings**—never from an arbitrary client-supplied `tenantId` header. `tenantId` is the **internal tenant ID**, whereas `authenticatedClientCode` is the partner-side client code bound to the trusted connection/principal. Payload `clientCode` is merely a **claimed value** that must be verified against the authenticated client code rather than compared directly with internal tenant IDs if the two systems use different codes.

### 10.2. Reference resolver with an explicit contract

~~~java
package example.partner.acl;

import java.util.Optional;

public interface ShipmentReferenceResolver {
    Optional<String> findInternalShipmentId(
            String partnerId,
            String tenantId,
            String bookingRef);
}
~~~

Mapping keys should include **partner + tenant + external reference** or a contract-guaranteed unique scope. Never do this:

~~~java
// WRONG unless a contract explicitly guarantees this rule:
String internalId = external.bookingRef().replace("SHIP-", "");
~~~

Partner codes can be reused, vary in length, collide across tenants, or change formats. Critical business data demands **authoritative identity mapping**, not guesswork string manipulation.

### 10.3. Concrete translator

~~~java
package example.partner.acl;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.Objects;

import example.partner.external.PartnerDeliveryEventV1;
import example.domain.delivery.DeliveryStatus;
import example.domain.delivery.DeliveryUpdate;

public final class PartnerDeliveryTranslator {
    private final ShipmentReferenceResolver references;

    public PartnerDeliveryTranslator(
            ShipmentReferenceResolver references) {
        this.references = Objects.requireNonNull(references);
    }

    public DeliveryUpdate toDomain(
            PartnerDeliveryEventV1 event,
            TrustedPartnerContext trusted) {

        if (event == null || trusted == null) {
            throw new InvalidPartnerContract("Missing event/context");
        }
        requireNonBlank(event.eventKey(), "eventKey");
        requireNonBlank(event.bookingRef(), "bookingRef");
        requireNonBlank(event.phase(), "phase");
        requireNonBlank(event.eventTime(), "eventTime");

        if (!trusted.authenticatedClientCode()
                .equals(event.clientCode())) {
            throw new InvalidPartnerContract("Tenant mismatch");
        }

        String internalId = references.findInternalShipmentId(
                trusted.partnerId(),
                trusted.tenantId(),
                event.bookingRef()
        ).orElseThrow(() ->
                new UnresolvedPartnerReference(event.bookingRef()));

        DeliveryStatus status = switch (event.phase()) {
            case "S1" -> DeliveryStatus.IN_TRANSIT;
            case "S2" -> DeliveryStatus.DELIVERED;
            case "R1" -> DeliveryStatus.RETURNED;
            default -> throw new InvalidPartnerContract(
                    "Unknown partner phase");
        };

        final Instant occurredAt;
        try {
            occurredAt = OffsetDateTime
                    .parse(event.eventTime())
                    .toInstant();
        } catch (DateTimeParseException ex) {
            throw new InvalidPartnerContract(
                    "Invalid event timestamp", ex);
        }

        return new DeliveryUpdate(
                event.eventKey(),
                internalId,
                status,
                occurredAt,
                trusted.tenantId()
        );
    }

    private static void requireNonBlank(
            String value, String name) {
        if (value == null || value.isBlank()) {
            throw new InvalidPartnerContract("Missing " + name);
        }
    }
}
~~~

Two illustrative exceptions:

~~~java
package example.partner.acl;

public class InvalidPartnerContract extends RuntimeException {
    public InvalidPartnerContract(String message) {
        super(message);
    }
    public InvalidPartnerContract(String message, Throwable cause) {
        super(message, cause);
    }
}

public class UnresolvedPartnerReference extends RuntimeException {
    public UnresolvedPartnerReference(String reference) {
        super("Unresolved external shipment reference: " + reference);
    }
}
~~~

In real Java projects, place each `public` top-level class/record/enum in **its own matching file**. Code blocks here are grouped conceptually rather than as a single file to paste verbatim.

### 10.4. Why NOT use a default enum branch?

~~~java
// WRONG: turns any unknown value into delivered.
DeliveryStatus status = switch (event.phase()) {
    case "S1" -> DeliveryStatus.IN_TRANSIT;
    default -> DeliveryStatus.DELIVERED;
};
~~~

If the partner adds `S3 = DELIVERY_FAILED`, the buggy code reports delivery succeeded. For business-impacting statuses, **unknown** values must raise a contract error for controlled quarantine/investigation. Even if business treats `UNKNOWN` as a genuine domain state, it must be **explicitly specified**, never used to mask partner drift.

## 11. Semantic Mapping: Traps Invisible to Type Checkers

| Semantic mismatch | External contract | Internal requirement | ACL approach |
|---|---|---|---|
| **Status** | `S2` has specific meaning | `DELIVERED` carries invariants | Version- and semantics-verified mapping. |
| **Identifier** | Partner `booking_ref` | Internal `shipmentId` | Scoped reference resolver. |
| **Time** | Local time with offset | `Instant` | Parse offset; reject zoneless timestamps if needed. |
| **Currency** | Minor units (e.g., cents) | `Money(currency, amount)` | Explicit scale/rounding and currency rules. |
| **Quantity** | Grams | Kilograms | Explicit units and precision handling. |
| **Null/absent** | Omitted field may mean “unchanged” | Domain update distinguishes `null` | Separate missing, null, and reset. |
| **Boolean** | `Y/N/U` | true/false/unknown | Never coerce unknown to false. |
| **Error** | `E409_DUP` | `AlreadyExists` or conflict | Context-aware error translator. |
| **Identity** | `clientCode` in payload | Authenticated tenant | Cross-check against trusted context. |
| **Ordering** | Arbitrary arrival order | Ordered/versioned state machine | Version/sequence/stale-event policy. |
| **Partial results** | Partner returns `ACCEPTED` | Domain needs `COMPLETED` | Never upgrade accepted into completed. |
| **Precision** | Decimal or float | Monetary exactness | `BigDecimal` and rounding policy. |

### 11.1. Currency example

If a partner returns `total_minor_units: 1099` with `currency: USD`, never divide by 100 as a `double` assuming every currency has two decimal places. Currencies vary in minor-unit exponents; convert per **contract** using a monetary library/`BigDecimal`. Reject negative values, overflows, precision loss, or unsupported currencies as needed.

### 11.2. Time example

`2026-11-23T09:00:00Z` and `2026-11-23T16:00:00+07:00` represent the exact same `Instant`. If a partner sends `2026-11-23 16:00:00` **without a zone**, define the source timezone in the contract—never silently rely on the JVM default timezone, which differs between local machines and CI.

## 12. Translation Must Separate Contract Validation from Domain Invariants

An event can be **schema-valid** yet **business-invalid**:

~~~json
{
  "event_key": "evt-100",
  "booking_ref": "SHIP-01",
  "phase": "S2",
  "event_time": "2026-11-23T16:00:00+07:00",
  "client_code": "customer-vn"
}
~~~

All fields above are present; yet if the shipment was already canceled or the internal state machine forbids `RETURNED → DELIVERED`, the domain must reject the transition.

~~~mermaid
flowchart TD
    RAW["Partner payload"] --> SCHEMA{"Valid schema/contract?"}
    SCHEMA -- "No" --> REJECT["Invalid contract<br/>quarantine"]
    SCHEMA -- "Yes" --> TRANSLATE{"Meaningful mapping?"}
    TRANSLATE -- "No" --> REJECT
    TRANSLATE -- "Yes" --> CMD["Internal command"]
    CMD --> DOMAIN{"Domain invariants hold?"}
    DOMAIN -- "No" --> BUSINESS["Business rejection<br/>conflict/ignored event"]
    DOMAIN -- "Yes" --> APPLY["Apply business transition"]
~~~

**The ACL is never a place to bypass domain invariants**. It translates so the domain receives well-formed requests; the domain decides whether state changes are permitted. Both error categories need distinct classifications in audit and retry policies.

## 13. Integrating ACL into Spring Integration Java DSL

Spring Integration provides building blocks such as `IntegrationFlow.from(...)`, `transform(...)`, `handle(...)`, `filter(...)`, `route(...)`, and `channel(...)`. Place the ACL **between decoded inbound payloads and application-facing channels**, or **before outbound gateways and after partner replies**.

### 13.1. Inbound flow: decoded message → translation → domain channel

~~~java
package example.partner.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

import example.partner.acl.InvalidPartnerContract;
import example.partner.acl.PartnerDeliveryTranslator;
import example.partner.acl.TrustedPartnerContext;
import example.partner.external.PartnerDeliveryEventV1;

@Configuration
@EnableIntegration
public class PartnerIngressConfig {

    // Receives only DTOs already decoded by a trusted adapter.
    @Bean
    DirectChannel decodedPartnerEvents() {
        return new DirectChannel();
    }

    // In production, leads to an application service.
    // In flow tests, QueueChannel can be used to observe outputs.
    @Bean
    QueueChannel internalDeliveryUpdates() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow deliveryIngressFlow(
            DirectChannel decodedPartnerEvents,
            QueueChannel internalDeliveryUpdates,
            PartnerDeliveryTranslator translator) {
        return IntegrationFlow.from(decodedPartnerEvents)
                .handle(PartnerDeliveryEventV1.class,
                        (payload, headers) -> {
                            Object value = headers.get(
                                    "verifiedPartnerContext");

                            if (!(value instanceof TrustedPartnerContext trusted)) {
                                throw new InvalidPartnerContract(
                                        "Missing trusted partner context");
                            }
                            return translator.toDomain(payload, trusted);
                        })
                .channel(internalDeliveryUpdates)
                .get();
    }
}
~~~

**Mandatory requirement:** the `verifiedPartnerContext` header in this example **must never come directly from client-controllable HTTP request headers or Kafka event headers**. The adapter/authentication boundary must verify source identity and attach this context via a secure internal convention; if input lacks a trusted context, the flow rejects it.

This is an **illustrative Spring Integration Java DSL pattern**, assuming `PartnerDeliveryTranslator` is a bean and the earlier DTOs/classes are defined. Typed `handle(...)` overloads may vary slightly by Spring Integration version. What stays invariant: **the application service sees only `DeliveryUpdate`, never `PartnerDeliveryEventV1`**.

### 13.2. Never wire external payloads straight into the domain

~~~java
// Anti-pattern: domain handler receives raw external DTO.
return IntegrationFlow.from(decodedPartnerEvents)
        .handle(partnerEvent -> domainService.applyPartnerEvent(partnerEvent))
        .get();
~~~

If the domain imports `PartnerDeliveryEventV1` and interprets `phase` itself, the protective boundary is bypassed. In simple systems, translator and application service may sit inside one handler, yet **translation responsibilities must remain cleanly separated and independently testable**.

### 13.3. Should a filter or translator handle unknown values?

A filter can drop messages, yet **silently filtering out** unknown statuses is usually an anti-pattern. When a partner adds a new code:

- Contract validators/translators should raise errors with reason codes and versions.
- Error flows decide whether to quarantine or await mapping updates.
- You need evidence the event wasn't applied, not merely “no output.”

Intentionally ignoring an event (e.g., irrelevant notifications) requires an **explicit rule** and metrics counting ignored events.

## 14. Outbound ACL and Response Translation

Suppose the domain wants to “reserve delivery,” while the partner uses `booking_ref`, `service_code`, and replies `state = "A"` or `state = "P"`.

### 14.1. Three separate models

~~~java
// Internal command:
public record ReserveShipmentCommand(
        String shipmentId,
        String tenantId,
        String serviceLevel) {
}

// Partner's request DTO:
public record PartnerReserveRequestV2(
        String partnerReference,
        String serviceCode) {
}

// Partner's reply DTO:
public record PartnerReserveResponseV2(
        String partnerBookingId,
        String state) {
}

// Internal result:
public record ShipmentReservationResult(
        String shipmentId,
        String reservationId,
        ReservationOutcome outcome) {
}
~~~

These records/enums belong in **separate packages/files** in real source trees. `ReservationOutcome` is a domain-defined enum per internal contract, never directly exposing partner codes `A` or `P`.

### 14.2. Outbound translator

~~~java
public final class PartnerReservationTranslator {

    private final PartnerReferenceRepository references;

    public PartnerReservationTranslator(
            PartnerReferenceRepository references) {
        this.references = references;
    }

    public PartnerReserveRequestV2 toPartner(
            ReserveShipmentCommand command) {
        String partnerReference = references
                .toPartnerReference(
                        command.tenantId(), command.shipmentId())
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "No partner shipment mapping"));

        String serviceCode = switch (command.serviceLevel()) {
            case "STANDARD" -> "STD";
            case "EXPRESS" -> "EXP";
            default -> throw new IllegalArgumentException(
                    "Unsupported service level");
        };

        return new PartnerReserveRequestV2(
                partnerReference, serviceCode);
    }

    public ShipmentReservationResult toDomainResult(
            String internalShipmentId,
            PartnerReserveResponseV2 response) {
        ReservationOutcome outcome = switch (response.state()) {
            case "A" -> ReservationOutcome.CONFIRMED;
            case "P" -> ReservationOutcome.PENDING;
            default -> throw new InvalidPartnerContract(
                    "Unknown reservation state");
        };
        return new ShipmentReservationResult(
                internalShipmentId,
                response.partnerBookingId(),
                outcome);
    }
}
~~~

The snippet **illustrates method contracts**; `PartnerReferenceRepository` and `ReservationOutcome` are project-defined interfaces/enums. When the partner reply only includes `partnerBookingId`, the ACL needs **request context or correlation** to link back to `internalShipmentId`—never guess internal IDs from reply codes.

### 14.3. Java DSL wiring an HTTP outbound gateway

~~~java
// Illustrative config; requires spring-integration-http module
// and imports for org.springframework.integration.http.dsl.Http,
// org.springframework.http.HttpMethod per your project version.

@Bean
IntegrationFlow reserveWithPartner(
        DirectChannel internalReservations,
        PartnerReservationTranslator translator) {

    return IntegrationFlow.from(internalReservations)
            // Must preserve request context here to correlate the reply.
            .transform(ReserveShipmentCommand.class,
                    translator::toPartner)
            .handle(Http.outboundGateway(
                        "https://partner.example/v2/reservations")
                    .httpMethod(HttpMethod.POST)
                    .expectedResponseType(PartnerReserveResponseV2.class))
            // Add a step mapping the reply using persisted request
            // correlation/context; never invent internal IDs from replies.
            .channel("partnerReservationResponses")
            .get();
}
~~~

**Important:** this configuration illustrates only outbound translation and the HTTP call; it omits the `toDomainResult` step because pairing **the original `internalShipmentId` with the reply** requires explicit correlation/persistence. Do not treat this as a complete production request/reply flow. Moreover, `partner.example` is a sample hostname; production configs must inject endpoints and managed secrets from secure environments.

### 14.4. What to test on request/reply

1. Internal command maps to partner request with exact schema and service codes.
2. External reference lookup is scoped to the right tenant.
3. HTTP method, path, headers, and body match the contract.
4. Response codes `A`/`P` map to clear internal outcomes.
5. Replies lacking correlation follow policy without guessing IDs.
6. Missing replies, timeouts, duplicate replies, or late replies never mix requests.
7. HTTP 202 or partner `PENDING` never gets promoted to internal `CONFIRMED`.
8. Side effects enforce idempotency/readbacks when retrying write operations.

## 15. One Canonical Model or Many?

A single `CanonicalOrderEvent` shared across all partners looks tempting to minimize DTOs. Yet an overly broad **enterprise-wide canonical model** often swells into a union of every vendor field—recreating the exact pollution the ACL was meant to block.

### 15.1. Internal models scoped to bounded contexts

~~~mermaid
flowchart LR
    A["Partner A contract"] --> ACL_A["ACL A"]
    B["Partner B contract"] --> ACL_B["ACL B"]
    C["Partner C contract"] --> ACL_C["ACL C"]
    ACL_A --> CMD["Delivery bounded context<br/>DeliveryUpdate"]
    ACL_B --> CMD
    ACL_C --> CMD
    CMD --> DOMAIN["Domain logic"]
~~~

**Recommendation:** design internal models tailored to a **specific bounded context**. Independent internal apps with distinct semantics should not be forced into one shared DTO merely because they pass through the same integration platform.

### 15.2. Cost trade-offs of canonical models

| Option | Pros | Risks |
|---|---|---|
| Direct partner DTO into domain | Less initial code | Vendor leakage, hard to swap partners. |
| Dedicated ACL per partner | Protects model, easy vendor swaps | Mapping and governance overhead. |
| Canonical model per bounded context | Reuse and stable internal contracts | Needs owner/versioning; don't cram every partner quirk. |
| Giant enterprise-wide canonical schema | Org-wide standardization | Global coupling, slow evolution, awkward semantic fits. |
| Event-driven integration with domain events | Loose coupling across contexts | Needs clear consistency/ordering/versioning. |

Pick models by **business language and ownership**, not merely matching field names.

## 16. Protecting Identity Boundaries and Ownership

An external ID might be:

- Unique only within one vendor account;
- Reused after a retention period;
- An integer whose format changes in API v2;
- An alias for an existing internal object;
- An identifier for a semantically different object despite a similar name.

### 16.1. Scoped mapping table

~~~sql
CREATE TABLE partner_shipment_reference (
    partner_id       VARCHAR(80) NOT NULL,
    tenant_id        VARCHAR(80) NOT NULL,
    external_ref     VARCHAR(160) NOT NULL,
    internal_id      VARCHAR(120) NOT NULL,
    mapping_version  INTEGER NOT NULL,
    PRIMARY KEY (partner_id, tenant_id, external_ref)
);
~~~

This is **illustrative DDL**, not a full production schema. Domains may also need uniqueness constraints, mapping history, effective dates, audits, soft deletes, or one-to-many mappings.

### 16.2. Verifying resolvers

- Partner A and Partner B both use `booking_ref = 100` pointing to different shipments.
- Two tenants share the same external ID without cross-reads.
- Unmapped partner code → `UNRESOLVED_REFERENCE`, never randomly creating a shipment.
- Mapping changes → track version and define which version older events use.
- Resolver cache goes stale after a mapping is revoked → invalidation or bounded TTL.
- Concurrent updates → prevent two internal objects receiving the same reference against invariants.

**Note:** an ACL may call an application service to resolve references; do not build a redundant distributed identity master if the source data already has an owner.

## 17. ACLs with Contract Versioning and Schema Evolution

External systems deploy versions independently. A solid ACL recognizes **contract versions** and maps them to consistent internal meanings when appropriate.

### 17.1. v1 and v2 example

~~~json
{
  "schemaVersion": 1,
  "booking_ref": "SHIP-2026-000428",
  "phase": "S2",
  "event_time": "2026-11-23T16:00:00+07:00"
}
~~~

~~~json
{
  "schemaVersion": 2,
  "shipment_reference": "SHIP-2026-000428",
  "delivery_state": "DELIVERED",
  "occurred_at": "2026-11-23T09:00:00Z"
}
~~~

Both events can express **Delivered**, yet only when the partner confirms their business meanings truly match.

### 17.2. Versioned mapping

| Change | ACL action | Does the domain need to change? |
|---|---|---|
| `booking_ref` → `shipment_reference` | v2 DTO/parser/mapping | No, if the ID keeps the same meaning. |
| `S2` → `DELIVERED` | v2 translator | No, if still Delivered. |
| Required timestamp offset added | v2 parser contract | Probably not. |
| New status `DELIVERY_FAILED` | Negotiate domain interpretation | Possibly, if domain needs a new state. |
| Partner changes ID uniqueness scope | Update resolver/key strategy | May require data migration. |
| Redefines `DELIVERED` to “arrived at hub” | Cannot just rename fields | Must revisit domain mapping/invariants. |

### 17.3. Safety rules

1. **Trusted version source:** header, content type, schema registry, or verified payload field per contract.
2. **Versioned mappings:** keep v1 and v2 isolated without hidden bleed-through.
3. **Never auto-accept unknown new versions permissively.**
4. **Keep compatibility tests and legacy fixtures** before deploying updated translators.
5. **Maintain version sunset plans** while monitoring remaining v1 traffic.
6. **Provide fallback/quarantine** for uninterpretable payloads.
7. **Separate schema compatibility from semantic compatibility:** fields can stay type-compatible while shifting meaning.

### 17.4. Recording version evidence

When mapping fails, audits should capture `partnerId`, contract version, event ID, error class, and payload hash/reference per security policy; avoid logging merely “invalid payload,” which makes investigating contract drift impossible.

## 18. ACL at File and SFTP Boundaries

File/SFTP commonly deliver CSV, XML, JSON, or fixed-width data with distinct challenges:

| Boundary | Error/risk | ACL/adapter responsibility |
|---|---|---|
| File readiness | Producer still writing | Adapter ingests only ready files per convention. |
| File encoding | UTF-8 vs. legacy encodings | Parser detects/normalizes per contract. |
| CSV schema | Column order, date/decimal formats | Versioned contract validator/translator. |
| Remote path | Client-influenced paths, traversal | Adapter validates paths within allowed scope. |
| File identity | Reused filenames | Durable event/business IDs and metadata. |
| Record identity | One file holding many orders | ACL maps each row with `sourceRef`/row number if needed. |
| Partial errors | 9 valid rows, 1 bad row | Define atomic batch vs. partial acceptance. |
| SFTP disconnect | Partial download | Retry/cleanup per adapter lifecycle. |
| Quarantine | Uninterpretable files | Persist safely with reason; never drop silently. |

### 18.1. One file is not necessarily one business transaction

Suppose a file holds 10,000 rows where 100 violate the contract. Decide between:

- **All-or-nothing:** reject the whole file; commit only if all rows validate.
- **Partial processing:** process 9,900 rows, quarantine 100 rows, emit reconciliation report.
- **Staged import:** parse and validate everything first, then apply in transactions/batches.

The ACL can emit **row-level canonical commands** and a validation report; atomicity and settlement belong to the use case and storage/transaction design. Tests must prove “file read” ≠ “all rows succeeded.”

### 18.2. Locating errors precisely

Error records should include `fileId`, `rowNumber`, `contractVersion`, `reasonCode`, and minimal authorized context. Never dump private keys, SFTP credentials, or full PII into debug logs.

## 19. ACL at HTTP Inbound and Outbound Boundaries

### 19.1. HTTP inbound gateway

An HTTP gateway maps JSON requests into `Message<ExternalDto>`; the ACL then:

1. Verifies schema/version/content type.
2. Reads trusted principal/tenant from the authenticated security layer.
3. Cross-checks claimed tenant in the payload if required by contract.
4. Maps the external command into an internal command.
5. Translates application outcomes back into external API response DTOs/status codes.

**Never pass public API DTOs straight into aggregates** just because controllers or HTTP gateways make it convenient.

### 19.2. HTTP outbound gateway

Outbound ACLs translate internal requests into partner requests and translate HTTP responses into **domain-meaningful outcomes**.

| HTTP response | Transport meaning | What the ACL must determine |
|---|---|---|
| 200 | HTTP request succeeded | Which business contract applies to the response body? |
| 201 | HTTP resource created | Are the returned resource ID and status sufficient? |
| 202 | Request accepted | Not automatically business-completed. |
| 400 | Invalid request per API | Schema/validation/quarantine or translator bug? |
| 401/403 | Authn/authz failure | Do not wastefully retry with the same credentials. |
| 404 | Not found | Permanent or eventual consistency per contract. |
| 409 | Conflict | Already processed, duplicate, or genuine conflict? |
| 429 | Rate limit | Retry/backoff per contract without causing storms. |
| 500/503 | Server failure | Bounded retries; idempotency/readbacks for writes. |
| Timeout after POST | Server outcome unknown | Unknown outcome and reconciliation. |

ACL/error translators must never turn every HTTP 2xx into **domain success** if the body says `REJECTED` or `PENDING`.

### 19.3. Client headers are untrusted data

Never trust `X-Tenant-Id` or `X-Role` from requests without an authentication/authorization boundary. Behind a trusted API gateway, enforce *strip and re-inject* conventions for security headers or verify signatures/mTLS by design to stop header spoofing through proxies.

## 20. ACL at JMS, AMQP, and Kafka Boundaries

### 20.1. All are messaging, yet semantics differ

| Aspect | JMS | AMQP | Kafka |
|---|---|---|---|
| Routing | Destinations, message selectors/providers | Exchanges, routing keys, bindings/queues | Topics, partitions, keys |
| Delivery state | Sessions/transactions/acks | ACK/NACK/requeue/confirms | Offsets/consumer groups/commits |
| Ordering | Per destination/provider/consumer setup | Per queue and concurrency | Within partitions, not topic-wide |
| Retries | Container redelivery/advice | Requeues/delayed retries/DLX | Consumer retries/DLT/reprocessing |
| Payload contract | JMS body/properties | AMQP body/properties/headers | Record keys/values/headers |

The ACL focuses on **payload meaning, business IDs, domain events, and error classification**, while adapters/containers own protocol ACKs/offsets and connection lifecycles.

### 20.2. External events arriving from Kafka

~~~mermaid
flowchart LR
    TOPIC["Partner Kafka topic<br/>ExternalEventV2"] --> CONSUMER["Kafka inbound adapter"]
    CONSUMER --> DECODER["Deserialize + schema check"]
    DECODER --> ACL["ACL: resolve ref,<br/>map meaning/status"]
    ACL --> EV["Internal DeliveryUpdate"]
    EV --> APP["Application service"]
    ACL --> ERROR["Contract error quarantine"]
    APP --> OUT["Side effect + idempotency"]
~~~

If the Kafka consumer commits offsets right after the ACL sends to a **non-durable** internal channel, crashes lose events. That is **transaction/delivery design**, not something guaranteed automatically by adding an ACL. Tests must verify **when sources ACK/commit relative to processing or durable recovery**.

### 20.3. Event IDs and keys

External Kafka keys drive partitioning, not internal entity IDs. The ACL may need `partnerId + tenantId + eventId` for dedupe and `externalRef → internalId` to update aggregates. Key selection affects ordering; changing keys can shift events for the same shipment across partitions.

### 20.4. Routing contract errors to DLT

Unknown statuses or invalid schemas are typically **non-transient**; retrying repeatedly achieves nothing. Route them to a DLT/quarantine with reason codes and redrive procedures after updating the translator. Still, **verify DLT publish succeeded** before ACKing source offsets when contracts forbid message loss.

## 21. ACL at JDBC/Database Boundaries

Never let a partner system's database schema **shape your internal domain schema**. A JDBC inbound adapter might read a legacy table:

~~~sql
SELECT ext_event_key, ext_order_ref, state_code, event_epoch_ms
FROM legacy_shipments
WHERE processed_flag = 0;
~~~

ACL:

- maps `ext_order_ref` via reference resolver;
- translates `state_code` per contract/version;
- normalizes `event_epoch_ms` into `Instant` with explicit millisecond units;
- emits `DeliveryUpdate` or a domain command;
- never leaks `processed_flag` as a domain attribute just because the source table has that column.

### 21.1. Polling, transactions, and consistency

| Scenario | Risk | Test to include |
|---|---|---|
| Row read twice | Duplicate side effects | Business idempotency. |
| Row marked processed before domain commit | Lost events on crash | Proper transactions/checkpoints. |
| Two pollers run same query | Duplicate claims | Row locks/leases/atomic updates. |
| Missing reference mapping | Event cannot be interpreted | Owned quarantine/retry policy. |
| Contract schema renames column | Silent mis-mapping | Contract/DB integration tests. |
| Timestamp unit shifts | Timestamps off by 1000x | Test epoch seconds vs. milliseconds. |
| Source database unavailable | Transient I/O | Adapter retry/backoff; never turn into domain validation error. |

**Separate failure classes:** an SQL connection timeout is an infrastructure error, whereas `state_code = "??"` is a semantic error. Catching both as `InvalidPartnerContract` causes wrong retry and ops responses.

## 22. Error Policies: Contract, Reference, Domain, and Transport

A well-designed ACL classifies failures to decide **retry, reject, quarantine, reconcile, or propagate**.

| Error | Origin | Example | Suggested handling |
|---|---|---|---|
| **TransportTransient** | Adapter/network | HTTP 503, dropped SFTP | Bounded retry/backoff; monitor outages. |
| **SerializationFailure** | Decoder/schema | Malformed JSON | Reject/quarantine; never retry verbatim. |
| **UnsupportedContractVersion** | ACL contract | Receives v5 when supporting v1–v2 | Quarantine and alert drift. |
| **UnknownExternalStatus** | Semantic mapping | `phase = "S9"` | Quarantine; owner confirms meaning. |
| **UnresolvedExternalReference** | Resolver | Unmapped `booking_ref` | Await reconciliation or reject per contract. |
| **TenantMismatch** | Trust boundary | Payload claims different tenant | Reject/security incident; never auto-fix tenant. |
| **DomainConflict** | Application/domain | Stale event or forbidden transition | Record business conflict; do not map to 503. |
| **UnknownOutcome** | Outbound/network | POST times out after send | Readback/idempotency prior to retry. |
| **RecoveryFailure** | DLQ/quarantine publisher | Failed to store error record | Escalate/propagate; never pretend handled. |

### 22.1. Business-meaningful internal error codes

~~~json
{
  "errorId": "err-789",
  "category": "CONTRACT",
  "code": "UNKNOWN_EXTERNAL_STATUS",
  "partnerId": "partner-a",
  "contractVersion": 2,
  "eventId": "evt-4280",
  "retryable": false,
  "state": "QUARANTINED"
}
~~~

This schema is an **internal template**, not an automatic Spring Integration payload. Never expose internal `partnerId`/exceptions/stack traces to public clients unless permitted by security policy.

### 22.2. When to return replies to external gateways?

For **request/reply gateways**, define:

- Return 4xx on contract/tenant validation errors.
- Return 409 on domain conflicts if specified by public contract.
- Return 5xx/503 on transient internal failures where appropriate.
- Return 202 or tracking IDs for asynchronous work; never call it completed.
- For unknown outcomes, return status/correlation to query later.

An `ErrorMessageSendingRecoverer` sending errors to a one-way channel **does not create an HTTP/JMS gateway reply**. When callers expect responses, error flows must map to valid replies to avoid false timeouts.

## 23. Retries, Idempotency, and ACL: Three Separate Responsibilities

**ACL** interprets external messages. **Retry** decides whether to re-attempt an operation. **Idempotency** protects side effects when the same operation executes repeatedly.

~~~mermaid
flowchart TD
    E["External event (eventId=E-1)"] --> A["ACL translation"]
    A --> ID["Identity/correlation + dedupe"]
    ID --> OP["Domain operation"]
    OP --> SIDE["Database/HTTP/Kafka side effect"]
    SIDE --> ACK{"Confirmed?"}
    ACK -- "No / timeout" --> VERIFY["Readback / retry policy"]
    VERIFY --> ID
    ACK -- "Yes" --> DONE["Verified outcome"]
~~~

### 23.1. An event can be redelivered many times

When JMS/AMQP/Kafka/File/SFTP redelivers the same logical event, Spring message IDs regenerate and broker delivery metadata changes, yet the **business `eventId`** must stay stable per contract if used for deduplication.

### 23.2. Never retry an external DTO by creating fresh unguarded internal commands

Scenario:

~~~text
E-1: external status S2 = delivered
ACL translates E-1 → DeliveryUpdate(eventId=E-1, status=DELIVERED)
Domain commits update successfully
Broker ACK is lost
Broker redelivers E-1
ACL translates the same command again
Domain deduplicates by business key/eventId, creating no duplicate side effect
~~~

Tests must assert both **delivery counts** and **business side-effect counts**, not just how often the mapper ran. The ACL doesn't have to own the dedup table—that usually sits in application/storage—yet **the ACL must preserve identity and never drop the idempotency key**.

### 23.3. Trade-offs when partners lack event IDs

Never blindly hash the entire payload as an event ID if partners can emit two distinct valid events with identical payloads. Negotiate contracts, pick meaningful composite keys, or establish owned inbox/reconciliation rules. Test all heuristics for collisions/false duplicates with explicit limits.

## 24. Trust Boundaries and Message Security

An ACL guards **semantics**, yet never replaces authentication, authorization, TLS, or secret management.

| Checkpoint | Purpose | Test |
|---|---|---|
| HTTP mTLS/OAuth/API keys | Verify callers/clients | Block unauthenticated requests from trusted channels. |
| SFTP host keys/auth | Verify server/partner identity | Reject unexpected host keys. |
| Kafka/JMS/AMQP ACLs/topic perms | Restrict publish/consume rights | Reject messages from wrong namespaces. |
| Trusted source identity | Bind accurate `partnerId` and `tenantId` | Never take principals from spoofable payloads. |
| Schema/size limits | Protect decoders/resources | Block oversized payloads and malicious inputs. |
| Path/URI validation | Prevent path traversal/SSRF | Never build arbitrary hosts/paths from user input. |
| Deserialization allowlists | Mitigate object deserialization risks | Allow only approved types/schemas. |
| Data classification | Govern storing/quarantining/logging PII | Prevent sensitive data leaks. |
| Rate limiting | Mitigate data floods/retry storms | Enforce per-source caps and alerts. |
| Audit/correlation | Trace events end-to-end | Record event IDs, verified tenants, and mapping outcomes. |

### 24.1. Never forward untrusted headers intact

External messages may inject `replyChannel`, `errorChannel`, or internal-looking headers. Inbound transport adapters **must never let clients steer internal channels via arbitrary headers**. At the boundary, map only allowlisted metadata and reconstruct trusted context—especially crucial when downstream handlers route by headers.

### 24.2. Never return raw domain exceptions to external APIs

Error translators must pick public error codes/statuses; never expose stack traces, connection strings, SQL queries, tokens, private keys, or other tenants' resources.

## 25. Managing Correlation, Auditing, and Observability

As events traverse adapters, preserve **identity across representations**:

~~~text
Partner event_key
    → ACL eventId
    → Internal operationId / shipmentId
    → HTTP Idempotency-Key
    → Kafka result-eventId
    → Audit / evidence reference
~~~

### 25.1. Audit sample

~~~json
{
  "traceId": "trace-2048",
  "partnerId": "partner-a",
  "tenantId": "VN",
  "externalEventId": "evt-4280",
  "externalReference": "SHIP-2026-000428",
  "internalShipmentId": "shp-2048",
  "contractVersion": 1,
  "translatorVersion": "delivery-acl-v4",
  "mappingOutcome": "TRANSLATED",
  "processingOutcome": "APPLIED",
  "targetEvidenceId": "domain-event-9901"
}
~~~

Log `externalReference`/`internalShipmentId` only if non-sensitive or properly protected; mask/hash/reference as needed. Failure logs should carry enough **reason and version** details without dumping entire raw payloads.

### 25.2. Metrics to monitor

| Metric | Helps detect | Caution |
|---|---|---|
| **ACL translation success rate** | Contract drift, mapping bugs | Slice by version/partner. |
| **Unknown enum count** | Partner added new states | Don't lump under “generic parsing error.” |
| **Unresolved reference backlog** | Missing reference mappings | Track age and owner, not just error counts. |
| **Tenant mismatch count** | Security/trust boundary violations | Alert with proper access controls. |
| **Quarantine count/oldest age** | Unprocessed events | Don't measure success only on cherry-picked events. |
| **Translator latency P95/P99** | Slow resolvers/transformers | Separate resolver I/O from CPU mapping. |
| **Contract version distribution** | Adoption and sunset progress | Never use event IDs as metric labels. |
| **Duplicate logical event rate** | Retries/redeliveries | Separate physical attempts from business operations. |
| **Business confirmation lag** | Slow final outcomes | Never equate with adapter send ACKs. |

### 25.3. Choosing metric labels

Use `partner`, `version`, `result`, `errorCategory`, `adapterType`, and `flowId` with controlled cardinality. Never put per-request `eventId`, `traceId`, or user IDs into metric labels; detailed correlation belongs in access-controlled **trace/log/evidence stores**.

## 26. Unit-Testing Translators with JUnit: Semantic Mapping Is the Goal

ACL unit tests should not depend on SFTP servers, Kafka brokers, or HTTP endpoints. The goal is verifying **external contract + trusted context + reference mapping → deterministic internal meaning**, and that uninterpretable inputs fail with clear reasons.

### 26.1. Happy path

~~~java
package example.partner.acl;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import java.util.Optional;
import org.junit.jupiter.api.Test;

import example.partner.external.PartnerDeliveryEventV1;
import example.domain.delivery.DeliveryStatus;
import example.domain.delivery.DeliveryUpdate;

class PartnerDeliveryTranslatorTest {

    private final ShipmentReferenceResolver references =
            (partnerId, tenantId, bookingRef) -> {
                if ("partner-a".equals(partnerId)
                        && "VN".equals(tenantId)
                        && "SHIP-2026-000428".equals(bookingRef)) {
                    return Optional.of("shp-2048");
                }
                return Optional.empty();
            };

    private final PartnerDeliveryTranslator translator =
            new PartnerDeliveryTranslator(references);

    private final TrustedPartnerContext verified =
            new TrustedPartnerContext(
                    "partner-a", "VN", "customer-vn");

    @Test
    void translatesPartnerDeliveryIntoInternalEvent() {
        PartnerDeliveryEventV1 external =
                new PartnerDeliveryEventV1(
                        "evt-4280",
                        "SHIP-2026-000428",
                        "S2",
                        "2026-11-23T16:00:00+07:00",
                        "customer-vn");

        DeliveryUpdate result =
                translator.toDomain(external, verified);

        assertEquals("evt-4280", result.eventId());
        assertEquals("shp-2048", result.shipmentId());
        assertEquals(DeliveryStatus.DELIVERED, result.status());
        assertEquals(
                Instant.parse("2026-11-23T09:00:00Z"),
                result.occurredAt());
        assertEquals("VN", result.tenantId());
    }

    @Test
    void rejectsUnknownStatusInsteadOfGuessing() {
        PartnerDeliveryEventV1 unknown =
                new PartnerDeliveryEventV1(
                        "evt-4281", "SHIP-2026-000428",
                        "S9", "2026-11-23T16:00:00+07:00",
                        "customer-vn");

        assertThrows(InvalidPartnerContract.class,
                () -> translator.toDomain(unknown, verified));
    }

    @Test
    void rejectsClientCodeThatDoesNotMatchTrustedSource() {
        PartnerDeliveryEventV1 forged =
                new PartnerDeliveryEventV1(
                        "evt-4282", "SHIP-2026-000428",
                        "S2", "2026-11-23T16:00:00+07:00",
                        "other-customer");

        assertThrows(InvalidPartnerContract.class,
                () -> translator.toDomain(forged, verified));
    }

    @Test
    void doesNotInventInternalIdForUnknownPartnerReference() {
        PartnerDeliveryEventV1 missing =
                new PartnerDeliveryEventV1(
                        "evt-4283", "SHIP-UNKNOWN",
                        "S2", "2026-11-23T16:00:00+07:00",
                        "customer-vn");

        assertThrows(UnresolvedPartnerReference.class,
                () -> translator.toDomain(missing, verified));
    }
}
~~~

Here `ShipmentReferenceResolver` is a functional interface (one abstract method), so a lambda works cleanly. These tests verify **partner codes, tenants, external IDs, statuses, timezones, and invalid inputs**; they do not yet prove JSON/file parsing or real source authentication.

### 26.2. Do not test only one enum value

Test the full `phase` table:

| Partner code | Internal status | Condition |
|---|---|---|
| `S1` | `IN_TRANSIT` | Confirmed by v1 contract. |
| `S2` | `DELIVERED` | Confirmed by v1 contract. |
| `R1` | `RETURNED` | Confirmed by v1 contract. |
| `S9` | Error `UNKNOWN_EXTERNAL_STATUS` | Never guess. |
| `null`/empty | Error `INVALID_CONTRACT` | Never pass through. |
| `s2` | Per case-sensitive policy | Do not auto-uppercase without contract backing. |

When v2 uses text instead of codes, write **separate versioned test fixtures** rather than adding a broad `default` branch hoping everything stays compatible.

## 27. Contract Tests, Snapshot/Golden Fixtures, and Version Drift

**Translator unit tests** verify conversion logic. **Contract tests** verify real external payloads and that serializers/parsers honor the wire contract: field names, numeric types, encodings, timestamps, required/optional fields, enums, and versions.

### 27.1. Using partner-published fixtures

~~~text
src/test/resources/contracts/partner-a/
  delivery-v1-success.json
  delivery-v1-missing-ref.json
  delivery-v1-unknown-phase.json
  delivery-v2-success.json
  delivery-v2-new-status.json
~~~

This list is a **sample layout**, not a requirement to create those files during authoring. In real projects, fixtures must track **governed partner contracts** with verified versions and origins.

### 27.2. Never let parsers hide contract bugs

Suppose v1 partner JSON uses `event_key`:

~~~json
{
  "event_key": "evt-4280",
  "booking_ref": "SHIP-2026-000428",
  "phase": "S2",
  "event_time": "2026-11-23T16:00:00+07:00",
  "client_code": "customer-vn"
}
~~~

If the Java DTO uses `eventKey` without `@JsonProperty("event_key")` or a naming strategy, deserialization silently leaves `eventKey = null`. A translator unit test constructing the DTO via its constructor **misses this serialization bug**.

Contract tests must decode **raw JSON fixtures** and assert fields before invoking the translator; for outbound, serialize external requests and assert **wire field names**, not just record getters.

### 27.3. Version sources and drift detection

| Scenario | Test to include |
|---|---|
| Partner v1 still arriving | v1 fixtures still decode/map per policy. |
| Partner adds optional field | Compatible or rejected per approved policy. |
| Partner drops required field | Missing fields never become dangerous defaults. |
| Partner changes integer to string | Parser/translator never silently coerces wrongly. |
| Partner changes meaning of existing enum | Semantic contract review and regression tests. |
| Partner sends unknown version | Quarantined/unsupported version with telemetry. |
| Partner changes timestamp representation | Test zone/offset/precision. |
| Partner changes source identifier scope | Test resolvers and migration mappings. |

**Schema compatibility does not equal semantic compatibility.** Type-valid JSON where `S2` changed meaning is a domain breaking change.

## 28. Spring Integration Flow Tests: Real ACL Logic, Mocked Transport

A valuable flow test runs:

~~~text
Message<PartnerDeliveryEventV1>
    → Contract validation
    → Reference resolver (fake store)
    → Real PartnerDeliveryTranslator
    → Message<DeliveryUpdate>
    → Observable QueueChannel
~~~

### 28.1. Channel test sample

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig({
        PartnerIngressConfig.class,
        PartnerIngressTestBeans.class
})
class PartnerAclIntegrationFlowTest {

    @Autowired
    @Qualifier("decodedPartnerEvents")
    DirectChannel input;

    @Autowired
    @Qualifier("internalDeliveryUpdates")
    QueueChannel output;

    @Test
    void translatesAtTheBoundaryAndPreservesTrustedContext() {
        TrustedPartnerContext trusted =
                new TrustedPartnerContext(
                        "partner-a", "VN", "customer-vn");

        PartnerDeliveryEventV1 external =
                new PartnerDeliveryEventV1(
                        "evt-4280", "SHIP-2026-000428",
                        "S2", "2026-11-23T16:00:00+07:00",
                        "customer-vn");

        boolean accepted = input.send(
                MessageBuilder.withPayload(external)
                        .setHeader("verifiedPartnerContext", trusted)
                        .setHeader("traceId", "test-trace-2048")
                        .build());

        assertTrue(accepted);
        Message<?> observed = output.receive(1_000);
        assertNotNull(observed);
        assertInstanceOf(DeliveryUpdate.class,
                observed.getPayload());

        DeliveryUpdate result =
                (DeliveryUpdate) observed.getPayload();
        assertEquals("shp-2048", result.shipmentId());
        assertEquals(DeliveryStatus.DELIVERED, result.status());
        assertEquals("VN", result.tenantId());
    }
}
~~~

`PartnerIngressTestBeans` is a test configuration **providing `PartnerDeliveryTranslator` and a fake `ShipmentReferenceResolver`**; this example is illustrative and not standalone-compilable without the classes/beans defined above.

**Security note:** this test injects `verifiedPartnerContext` from trusted test code to verify flow logic. It **does not prove** external HTTP callers are blocked if they try sending a header with the same name. To prove trust boundaries, test the actual inbound adapter/auth layer ensuring untrusted headers are stripped and context is constructed only post-authentication.

### 28.2. Why write at least two flow tests?

- **Happy path:** valid payload → valid `DeliveryUpdate`.
- **Negative path:** wrong tenant / unknown external state → **zero domain side effects**, error/rejection routed per design.

With `DirectChannel`, exceptions unwind to the caller. With `ExecutorChannel`/pollers, error paths run asynchronously; tests must inspect the actual `ErrorMessage`/recovery channel rather than assuming `send()` not throwing equals success.

## 29. Adapter Integration Tests: Verifying Protocols Flow Tests Cannot Prove

| Adapter | Suitable fixture | Pass evidence |
|---|---|---|
| **File** | `@TempDir`, ready files, real parser | Ready files processed; partial files skipped. |
| **SFTP** | Test SFTP server, test host key/credentials | Remote files fetched/sent properly; reconnects per policy. |
| **HTTP inbound** | HTTP client/test server or MockMvc where apt | Status/body/headers, auth, input mapping. |
| **HTTP outbound** | HTTP stub/test server | Method, path, body, reply status, TLS/timeouts where needed. |
| **JMS** | Test broker | Destinations, JMS properties, transactions, ack/redelivery. |
| **AMQP** | Test RabbitMQ broker | Exchanges/routing, ack/nack, confirms, DLX. |
| **Kafka** | Test Kafka broker | Topic/key/partition/schema, offsets/commits, DLT. |
| **JDBC** | Test DB matching prod engine where needed | Queries, mappings, transactions, locks, claims/restarts. |

**A passing flow test does not prove transport integration.** A mocked outbound handler receiving `PartnerReserveRequestV2` never proves the HTTP serializer emitted `snake_case` or that Kafka keys routed to the right partition.

### 29.1. Stateful fault injection

Transport tests should cover:

1. Source unavailable with bounded adapter retries/backoff.
2. Decoder/schema failures routed to meaningful error paths.
3. ACL unknown statuses quarantined rather than “fixed” by infinite transport retries.
4. Side effects succeed while response/ACK is lost → idempotency and readbacks.
5. Restarts before/after checkpoints → no dropped items or unintended duplicate side effects.
6. Recovery path itself failing → source messages never marked handled without durability.

## 30. Comprehensive ACL Test Matrix

| # | Scenario | Layer | What to verify |
|---:|---|---|---|
| 1 | Partner status `S1` | Unit | Maps accurately to `IN_TRANSIT`. |
| 2 | Partner status `S2` | Unit | Maps accurately to `DELIVERED`. |
| 3 | Unknown status `S9` | Unit | Rejected; never defaults wrongly. |
| 4 | Missing external event key | Unit | Invalid contract. |
| 5 | Empty external reference | Unit | Invalid contract. |
| 6 | Wrong client code | Unit/security | Tenant mismatch; no command emitted. |
| 7 | Unresolved reference | Unit/integration | Never invents internal IDs via heuristics. |
| 8 | Partners A/B share external ref | Resolver test | Mappings isolated per partner. |
| 9 | Tenants A/B share external ref | Resolver test | Mappings isolated per tenant. |
| 10 | Reference changed after caching | Resolver integration | Cache invalidation/TTL per contract. |
| 11 | Timestamp with `+07:00` | Unit | Accurate UTC `Instant`. |
| 12 | Timestamp without offset | Unit | Rejected or uses explicit contract zone. |
| 13 | Invalid timestamp | Unit | Reasoned error; never defaults to `now`. |
| 14 | Decimal currency precision | Unit | Zero unit/precision loss. |
| 15 | Missing vs. null field | Contract | Accurate update/clear semantics. |
| 16 | V1 JSON `snake_case` | Contract | Deserializes properly into Java DTO. |
| 17 | V2 schema | Contract | Decodes and translates per version. |
| 18 | Unknown contract version | Contract | Quarantined/unsupported. |
| 19 | Same field type, changed meaning | Semantic regression | Schema pass never masks domain break. |
| 20 | Valid inbound flow message | Spring flow | Accurate domain payload/headers. |
| 21 | Invalid inbound flow message | Spring flow | Zero domain side effects. |
| 22 | Spoofed trusted context header over HTTP | HTTP security | Stripped/rejected; wrong tenant blocked. |
| 23 | Valid outbound command | Unit/flow | Partner DTO carries right status/service code. |
| 24 | Unsupported outbound service code | Unit | Rejected prior to remote call. |
| 25 | HTTP reply `PENDING` | Contract | Never mapped to completed. |
| 26 | HTTP 202 | HTTP integration | Accurate pending/accepted semantics. |
| 27 | HTTP 400 invalid request | HTTP integration | Error classified; no blind retries. |
| 28 | HTTP 503 transient | HTTP integration | Bounded retry/backoff. |
| 29 | HTTP timeout after POST | E2E | Readback/idempotency; no duplicates. |
| 30 | File not ready | File integration | Partial file never read. |
| 31 | File with bad row | File integration | Clear atomic/partial error policy. |
| 32 | SFTP disconnect | SFTP integration | Clean reconnect/partial transfer handling. |
| 33 | JMS redelivery | JMS integration | No duplicate side effects. |
| 34 | AMQP DLQ | AMQP integration | Actual failed message lands in queue. |
| 35 | Kafka schema drift | Kafka integration | Proper reject/quarantine; sound offset policy. |
| 36 | Out-of-order Kafka messages | Domain integration | Stale events handled per policy. |
| 37 | JDBC two pollers on one source | DB integration | Sound claims/transactions. |
| 38 | Illegal domain state transition | Domain test | Domain rejects; ACL never bypasses. |
| 39 | Same event ID redelivery | Domain/inbox | Idempotency. |
| 40 | Quarantine publisher failure | Recovery integration | No false ACK. |
| 41 | Contracts v1/v2 running side by side | Migration test | Each version maps accurately. |
| 42 | Shadow comparison of v1/v2 mappings | Migration | Shadow run triggers zero side effects. |
| 43 | ACL version rollback | Migration | Pending events are not lost. |
| 44 | Secrets in error payload | Security | Redacted with restricted access. |
| 45 | Cross-tenant ID lookup | Security | No cross-tenant data leakage. |
| 46 | Parallel flow test | Isolation | No shared mutable state bugs. |
| 47 | Restart with persistent metadata | Recovery | Checkpoints and dedupe survive. |
| 48 | Disallowed fallback schema | Contract | Never guesses or returns fake success. |
| 49 | Rising resolver latency | Performance | SLOs and degradation policies in place. |
| 50 | Target completed while upstream ACK lost | E2E | Reconciliation yields accurate final state. |

You don't need to run every item against every transport. Tie each test to **the exact component under test**, test data, expected outcome, timeout, cleanup, and evidence. Asserting “no exception thrown” proves neither accurate ACL mapping nor that the target received and persisted data.

## 31. Case Study: Multi-Protocol Delivery Partner

### 31.1. Context

An internal platform manages shipments. **Partner A** drops CSV files over SFTP every 15 minutes using `booking_ref`/`S1`/`S2`. **Partner B** sends Kafka JSON events using `shipment_reference` and `DELIVERY_COMPLETED`. Internally, the domain understands only `DeliveryUpdate` with `shipmentId`, `status`, `occurredAt`, and `tenantId`.

~~~mermaid
flowchart LR
    A["Partner A<br/>SFTP CSV"] --> S["SFTP/File adapters"]
    B["Partner B<br/>Kafka JSON"] --> K["Kafka inbound adapter"]
    S --> PA["ACL A<br/>CSV/phase/reference"]
    K --> PB["ACL B<br/>JSON/status/reference"]
    PA --> INTERNAL["Internal DeliveryUpdate"]
    PB --> INTERNAL
    INTERNAL --> VALID["Domain invariant + inbox dedupe"]
    VALID --> STORE["Shipment aggregate / persistence"]
    STORE --> EVENTS["Internal domain event"]
~~~

Each ACL speaks **its partner's language**; both emit **one semantically consistent internal model**, without forcing Partner B to adopt Partner A's `S2` code.

### 31.2. Partner A: SFTP

Workflow:

1. Poll SFTP once files are marked ready.
2. Fetch to local folders/streams per configuration without trusting bare filenames as business IDs.
3. Parse/validate each CSV row, contract version, and encoding.
4. Match source connection against trusted partner/tenant.
5. Resolve `booking_ref`, translating `S2` to `DELIVERED`.
6. Pass `DeliveryUpdate` to the application service with event-ID deduplication.
7. Reconcile successful/failed rows per atomicity policy; quarantine failures with reasons.

### 31.3. Partner B: Kafka

Workflow:

1. Consumer receives records from the authorized topic/partition/tenant.
2. Decoder/registry validates schema v2 and enum values.
3. Construct trusted source context from approved broker identity/connection settings.
4. ACL B translates `DELIVERY_COMPLETED` to `DELIVERED` and resolves internal shipment IDs.
5. Domain enforces stale-event and dedupe rules.
6. Commit offsets or persist durable recovery per policy, never ACKing unhandled errors when loss is forbidden.

### 31.4. What must NEVER happen

- Domain `if/else` reading `S2` or `DELIVERY_COMPLETED` directly.
- Colliding external IDs from two partners treated as the same shipment.
- Local CSV timestamps parsed using the host machine's default timezone.
- Unknown statuses defaulting to `DELIVERED`.
- Kafka schema errors retrying endlessly without quarantine.
- Completed business events applied twice on source redelivery.

### 31.5. Acceptance evidence

| Evidence | Source |
|---|---|
| File/Kafka record received from source | Adapter transport evidence. |
| External contract version valid | Decoder/contract validator. |
| Partner reference resolved | Reference store/tracing. |
| Canonical internal event accurate | ACL unit/flow tests. |
| Valid domain transitions | Domain tests/DB state. |
| No duplicate side effects | Inbox/idempotency store and readbacks. |
| Failed events preserved | Persisted quarantine/DLT records. |
| No backlog loss on restart | Recovery/transport tests. |

## 32. Case Study: Swapping HTTP Providers Without Changing the Domain

### 32.1. Current state

Domain issues `ReserveShipmentCommand` currently backed by Partner A:

~~~text
ReserveShipmentCommand
   → ACL Partner A
   → HTTP API A POST /v1/bookings
   → Partner A reply
   → ShipmentReservationResult
~~~

The team wants to migrate to Partner B, whose endpoint is `/v2/reservations`, using `priority = HIGH/NORMAL` instead of `service_code` and returning `status = QUEUED/ACTIVE`.

### 32.2. Gradual swap strategy

~~~mermaid
flowchart TD
    CMD["Internal ReserveShipmentCommand"] --> ROUTE{"Partner routing policy"}
    ROUTE -- "Cohort A" --> A["ACL A + HTTP Gateway A"]
    ROUTE -- "Cohort B" --> B["ACL B + HTTP Gateway B"]
    A --> MAPA["A reply translator"]
    B --> MAPB["B reply translator"]
    MAPA --> RES["ShipmentReservationResult"]
    MAPB --> RES
~~~

The rest of the domain must never contain:

~~~java
if (partner.equals("B")) {
    // Domain understands QUEUED/ACTIVE of a new vendor.
}
~~~

Instead, routing lives in **application/integration policy**, while Translator B maps statuses and errors; the domain knows only `PENDING`, `CONFIRMED`, or designed internal outcomes.

### 32.3. Shadow mode must NEVER create duplicate side effects

When running A and B side by side to compare mappings, avoid **sending two real booking requests** that create two shipments. Instead:

- Run Translator B in **dry-run** mode on redacted requests without calling the live create API.
- Compare fields expected to be semantically equivalent.
- Test B against a dedicated sandbox/test tenant with isolated IDs.
- Flip cohorts via feature flags only after contracts and side effects are verified.

**Never declare shadow traffic safe solely because a request has `X-Shadow: true`** unless the partner guarantees zero side effects.

## 33. Migrating to an ACL from an Unbounded Legacy Architecture

Legacy systems often scatter vendor mappings across services, repositories, and message listeners. No big-bang rewrite is needed.

### 33.1. Controlled migration steps

1. **Inventory:** locate external types, status codes, SQL tables, and protocol headers leaking into the domain.
2. **Establish internal vocabulary:** align commands/results/events and invariants with domain owners.
3. **Isolate one use case:** pick one high-impact flow with a well-understood contract.
4. **Add boundary translators:** keep domain public interfaces stable while moving vendor conversions outward.
5. **Characterization tests:** lock down existing good behavior and known bugs.
6. **Contract tests:** use real/sandbox partner fixtures covering v1/v2 and failures.
7. **Side-effect-free dual-run or shadow validation:** compare before/after mappings safely.
8. **Feature flag/canary:** shift one cohort gradually with a rollback plan.
9. **Monitor unknown/compat drift:** watch quarantine, mismatches, and target outcomes.
10. **Remove old coupling:** strip vendor DTO/enum imports from the domain once all flows migrate and tests pass.

### 33.2. Rollback criteria

- Abnormal spike in `UNKNOWN_EXTERNAL_STATUS` or unresolved references.
- Domain transitions diverge from approved baselines.
- Rising duplicates, unknown outcomes, or cross-tenant errors.
- Partner v1/v2 mappings break compatibility.
- Target side effects fail reconciliation.

Rollback is more than flipping a flag: account for **messages waiting in channels/brokers**, serialized payload versions, and idempotency state. If the old version cannot read events emitted by the new version, rolling back causes new failures—tests must verify backward compatibility.

## 34. Common Anti-Patterns When Designing ACLs

| Anti-pattern | Consequence | How to improve |
|---|---|---|
| Domain imports external DTOs | Vendor schema changes break core. | Pass only internal commands/events across boundaries. |
| Calling DTO field renaming a full ACL | Fails to resolve semantic mismatches. | Separate state/ID/time/unit/error translation. |
| Using external enums in the domain | `S2`/`S9` infect business code. | Dedicated domain enums/value objects. |
| Defaulting unknown statuses to success | Applies false business states. | Reject/quarantine unknown semantics. |
| Guessing internal IDs from string prefixes | Collisions, cross-tenant leaks, mis-mapping. | Scoped/owned reference resolvers. |
| Trusting self-declared tenant IDs in payloads | Cross-tenant data leaks and mutations. | Trusted context + claim verification. |
| Ignoring timezones when parsing times | Events apply early/late. | Contract-defined offsets/zones using `Instant`. |
| Using `double` for money | Precision/rounding bugs. | `Money` value objects + `BigDecimal` policies. |
| Bloated enterprise canonical schemas | Global coupling and vendor fields pollute “standards.” | Context-scoped canonical models + per-partner ACLs. |
| Putting all business logic inside the ACL | Two conflicting sources of truth. | Domain owns invariants; ACL owns translation. |
| Hiding transactions/network inside converters | Hard unit tests; blurry retry boundaries. | Separate pure translation from resolver/service I/O. |
| Catching all exceptions as invalid contract | Wrong transport retry behavior. | Separate transport, contract, domain, and unknown outcomes. |
| Blindly retrying POST timeouts | Duplicate side effects. | Idempotency/readbacks and reconciliation. |
| Quarantine logs and drops messages | Data lost on restart. | Durable recovery and redrive. |
| Updating ACL without testing parsers | JSON `snake_case` silently nulls fields. | Raw payload contract tests. |
| Testing only the happy path | Unknown codes/duplicates/drift slip through. | Negative, concurrency, and recovery tests. |
| Mapping 202 responses to completed | Corrupted workflow states. | Separate pending/accepted domain outcomes. |
| Shadow calls hitting live write APIs | Double records/side effects. | Dry-run mapping or isolated sandboxes. |
| No owner for contract mappings | Nobody confirms meaning of new codes. | RACI, domain reviews, and version governance. |
| Logging raw payloads and tokens | Sensitive data exposure. | Redaction, data minimization, access controls. |

## 35. Architectural Decisions: Assigning Clear Responsibilities and Ownership

A solid ACL needs more than mapper code; it needs **decision rules and accountable owners** so it never rots into an untouchable pile of `if/else` branches.

| Decision | Stakeholders involved | Required evidence |
|---|---|---|
| Meaning of external statuses | Partner contract owner + domain owner | Approved versioned mapping matrix. |
| Internal domain vocabulary | Domain owner | Models/invariants and use-case tests. |
| Identifier uniqueness/scope | Domain/data owner + integration team | Reference schema/constraints and migration plans. |
| Trusted partner/tenant mapping | Security/identity + integration team | Auth/source identity and authorization tests. |
| Retryable failures | Operations/integration + domain owner | Retry/error policies and idempotency analysis. |
| Quarantine and redrive | Operations/data governance | Durability, ownership, retention, access controls. |
| Contract version sunset | Partner owner + product/domain | Usage metrics, compatibility tests, cutoff dates. |
| Backward-compatible rollout | Platform/integration + partner owner | Canaries/rollbacks/evidence. |
| Business reconciliation | Domain owner + operations | Target readbacks and exception workflows. |

### 35.1. Short decision record template

~~~yaml
# Illustrative decision record; not Spring Integration configuration.
decision:
  id: ACL-DELIVERY-004
  title: Translate partner phase S2 to internal DELIVERED
  scope:
    partner: partner-a
    contractVersion: 1
    internalBoundedContext: shipment
  interpretation:
    externalValue: S2
    internalValue: DELIVERED
    confirmedBy: partner-contract-owner
  prerequisites:
    - verified-source-tenant
    - resolved-internal-shipment-id
    - valid-event-timestamp
  unsupportedValuePolicy: QUARANTINE
  evidence:
    - contract-fixture-v1
    - semantic-regression-test
    - partner-acceptance-record
  supersedes: null
~~~

This is a **decision record template**. Fill `confirmedBy` with real owners/evidence in your project rather than treating sample placeholders as production sign-off.

### 35.2. When should an ACL say “I don't know”?

An ACL must never guess when:

- A partner sends an undefined new status.
- An external ID cannot resolve an internal entity.
- Units, currencies, or timezones are missing or contradictory.
- Payload tenant mismatches the authenticated connection.
- A reply returns `ACCEPTED` when the domain requires `COMPLETED`.
- The contract version is unsupported.

Not knowing is a **valid technical/semantic state to handle**, not an excuse to invent default data. Depending on risk, quarantine the message, await mapping updates, return an error to the caller, or trigger reconciliation.

## 36. Handling a Contract Drift Incident

Suppose a partner begins sending `phase = "S9"` while the ACL only knows `S1`, `S2`, and `R1`.

### 36.1. Detect and preserve

1. Schema decoder receives a structurally valid message.
2. ACL encounters the unknown phase and raises `UNKNOWN_EXTERNAL_STATUS`.
3. The error flow **does not** turn it into `DELIVERED` and does not silently drop it.
4. Persist a quarantine/failed reference with access controls, contract version, and correlation.
5. Retry classifier recognizes this error **cannot be fixed by immediately retrying the same payload**.
6. Operations receives threshold-based alerts; source ACK/offset follows the **durable recovery policy**.

### 36.2. Verify semantics

The integration team asks the contract owner what `S9` means and which internal state it relates to. The domain owner decides whether to:

- Map `S9` to an existing state if semantics truly match.
- Add a new state/domain event if it represents an important new concept.
- Record it purely as metadata/audit without mutating aggregates if the domain doesn't need it.
- Reject if the partner violated the contract and demand an upstream fix.

### 36.3. Deploy and redrive

1. Create an `S9` fixture plus negative/positive unit tests.
2. Run raw-payload contract tests and mapping tests.
3. Update the versioned translator without altering legacy `S2` mappings.
4. Deploy via canary or controlled rollout.
5. Redrive messages from quarantine with original `eventId`, verifying stale-version and idempotency guards.
6. Confirm internal state and final outcomes before resolving quarantine records.

### 36.4. Avoid creating a retry storm

If thousands of `S9` messages arrive within minutes, immediate retries spike load and clog queues. Use owned quarantine, aggregated alerts, and post-fix redrive. This illustrates how **ACL, retries, error handling, and operations complement each other** rather than replacing one another.

## 37. Reusable Integration Boundary Specification Template

~~~yaml
# Learning template: not a Spring Integration application.yml.
aclBoundary:
  id: partner-a-delivery-v1
  ownerTeam: integration-platform
  language: en

  externalContext:
    partnerId: partner-a
    protocol: SFTP
    schemaVersion: 1
    sourceIdentity: authenticated-sftp-account
    payloadType: PartnerDeliveryEventV1
    readinessRule: ready-marker

  trust:
    verifiedContext:
      - partnerId
      - tenantId
      - authenticatedClientCode
    claimedFields:
      - clientCode
    mismatchPolicy: REJECT

  translation:
    input: PartnerDeliveryEventV1
    output: DeliveryUpdate
    identityResolver: ShipmentReferenceResolver
    status:
      S1: IN_TRANSIT
      S2: DELIVERED
      R1: RETURNED
    unknownStatus: QUARANTINE
    timestampRule: REQUIRE_OFFSET
    preserve:
      - eventId
      - traceId
      - contractVersion

  errors:
    invalidContract: QUARANTINE
    unresolvedReference: RECONCILE
    domainConflict: DOMAIN_REJECTION
    transientTransport: BOUNDED_RETRY
    unknownOutboundOutcome: READBACK_BEFORE_RETRY

  delivery:
    businessIdempotencyKey:
      - tenantId
      - partnerId
      - eventId
    durableRecoveryRequired: true
    replayRequiresAuthorization: true

  verification:
    - translator-unit-tests
    - raw-contract-fixtures
    - spring-integration-flow-tests
    - sftp-adapter-integration-tests
    - restart-and-redrive-tests
    - security-boundary-tests

  observability:
    metrics:
      - translation_result
      - unknown_status
      - unresolved_reference
      - quarantine_oldest_age
      - confirmed_processing_latency
    redactRawPayload: true
~~~

### 37.1. How to use the template

Every entry needs a **contract owner and evidence**. For instance, `RECONCILE` must state who reconciles, where pending records live, and SLAs; `QUARANTINE` must define durability, retention, and redrive permissions; `REQUIRE_OFFSET` must be tested with both valid and invalid timestamps.

Never drop this YAML into an app expecting Spring to auto-generate endpoints. It is an **architectural and testing blueprint** to implement as configurations, translators, repositories, flows, and runbooks.

## 38. Practice Exercises

### Exercise 1 — Separating adapters and ACL

For `SFTP CSV → Spring Integration → Order Service`, draw both boundaries:

1. **Transport:** SFTP sessions, remote directories, file readiness, parsers.
2. **Semantic:** statuses, IDs, units/time, tenants, business commands.

Specify which layer may import external DTOs; may the domain know `phase = "S2"`? Explain what happens when the two layers mix.

### Exercise 2 — Designing a safe translator

Create `PartnerDeliveryEventV1` and `DeliveryUpdate` as in the examples, adding a partner v2 `DELIVERY_FAILED` status.

Requirements:

1. Define the v2 DTO and owned mapping rules.
2. Write tests for v1/v2, unknown statuses, and offset-less timestamps.
3. Never default unknown codes to a success status.
4. Use a resolver for external references.
5. Verify tenant claims against trusted context.

### Exercise 3 — Unit and flow tests

Build a Spring Integration `IntegrationFlow` with an input channel, translator, and output channel.

Requirements:

1. Unit-test the translator without a Spring context.
2. Flow-test with `DirectChannel` and `QueueChannel`.
3. Send messages with a fixture-created trusted context.
4. Assert outputs are internal commands/events, never external DTOs.
5. Send an unknown status, verifying the error path and zero domain side effects.
6. Explain why this test does not yet prove real SFTP/Kafka integration.

### Exercise 4 — Contract versioning

Partner evolves v1 (`booking_ref`, `S2`) to v2 (`shipment_reference`, `DELIVERED`).

Requirements:

1. Create two raw JSON fixtures.
2. Decode with a real configured serializer/parser.
3. Map both to the same internal `DeliveryUpdate` when semantics match.
4. Introduce a change keeping the same data type while altering meaning; verify detection.
5. Propose how to sunset v1 and roll back v2 without losing pending events.

### Exercise 5 — Multi-tenant reference resolver

Create table `partner_shipment_reference` with two tenants A/B and two partners P/Q.

Requirements:

1. Same external reference appears across multiple scopes.
2. Test resolution accuracy per scope.
3. Test missing mappings, revoked mappings, and stale caches.
4. Design uniqueness constraints and change audits.
5. Keep prefix-guessing ID logic out of the domain.

### Exercise 6 — HTTP outbound request/reply

Create `ReserveShipmentCommand` and two partner DTOs.

Requirements:

1. Outbound translator maps service levels to partner codes.
2. HTTP test server asserts method/URI/body/headers.
3. Partner returns `PENDING`; domain result must **not** be treated as completed.
4. Simulate HTTP 503, 429, 400, and read timeouts after POST.
5. Design idempotency/readbacks and verify side effects happen once logically.
6. Link the original internal shipment ID to the reply via controlled correlation.

### Exercise 7 — Multi-partner File/SFTP/Kafka

Partner A sends CSV via SFTP; Partner B sends JSON via Kafka. Both update shipment status.

Requirements:

1. Design two independent adapters/ACLs.
2. Both emit semantically consistent `DeliveryUpdate` objects.
3. Test file readiness, Kafka schema/topic/offset, and error/recovery.
4. Test duplicate event IDs and out-of-order status arrivals.
5. Test tenant isolation and unknown statuses per partner.
6. Identify which parts require real servers/brokers.

### Exercise 8 — Migrating from a legacy integration

The system currently runs `if ("S2".equals(event.phase()))` across three application services.

Requirements:

1. Identify leaky abstractions in the design.
2. Create an appropriate translator and domain model.
3. Write characterization tests before refactoring.
4. Design canaries, side-effect-free shadow validation, and rollbacks.
5. Document RACI for partner contracts vs. domain mappings.
6. Propose metrics to detect semantic drift.

### Exercise 9 — Real contract drift incident

A partner adds code `S9` unannounced. Build:

- Detection at the contract/semantic layer.
- Durable quarantine and error codes.
- A retry classifier avoiding pointless loops.
- Semantic verification workflow with partner/domain owners.
- Translator version updates and regression tests.
- Authorized, audited, idempotent redrive.
- Incident closure criteria after target readbacks.

### Exercise 10 — Architecture evaluation

Write an **Architecture Decision Record (ADR)** choosing among:

- Using external DTOs directly in the domain.
- A dedicated ACL per partner.
- One enterprise canonical model across all systems.

Cover context, options, evaluation criteria, mapping costs, ownership, versioning, operations, testing, and triggers to revisit the decision.

## 39. Boundary ACL Acceptance Checklist

- [ ] **External and internal bounded contexts are defined** without mixing vocabularies.
- [ ] **Domain imports zero unnecessary external DTOs, exceptions, or protocol headers.**
- [ ] **Transport adapters and semantic translators hold distinct responsibilities.**
- [ ] **Internal commands/events/results have clear semantics** confirmed by domain owners.
- [ ] **External IDs resolve within partner/tenant scopes**, never guessed from strings.
- [ ] **Trusted contexts are created post-authentication/source verification**, never trusting client headers.
- [ ] **Status/enum mappings are explicit**; unknowns never default to success.
- [ ] **Time/unit/currency conversions are specified** without arbitrary default timezones/precision.
- [ ] **Contract validation is separated from domain invariant validation** with distinct error categories.
- [ ] **Inbound and outbound translation** exist wherever connections flow.
- [ ] **Reply correlation is accurate**; accepted/pending states never upgrade to completed.
- [ ] **Schemas and semantics are version-managed**, testing v1/v2 coexistence where needed.
- [ ] **Raw-payload contract tests exist**, not just unit tests with hand-built DTOs.
- [ ] **Spring Integration flow tests exist** covering channel wiring and negative paths.
- [ ] **Adapter integration tests cover real transports:** File, SFTP, HTTP, JMS, AMQP, Kafka, JDBC.
- [ ] **Idempotency/duplicate/stale-event policies exist**, especially across redeliveries/restarts.
- [ ] **Explicit retry/error/quarantine/reconciliation paths** avoid treating unknowns as transient errors.
- [ ] **Quarantine and DLT enforce durability, retention, and access controls** as required.
- [ ] **Never report success merely on message send**; target readbacks/evidence exist where needed.
- [ ] **Tracing/correlation and metrics exist** with bounded cardinality and redacted PII/secrets.
- [ ] **Owners sign off on semantic mappings** rather than guessing from field names.
- [ ] **Migrations/canaries/rollbacks are tested** without side effects during shadow runs.
- [ ] **Test fixtures are isolated, bounded by timeouts, and cleaned up**, never touching production resources.
- [ ] **Checklists/risk reviews exist** whenever partner contracts add fields, statuses, versions, or shift meanings.

## 40. Summary

An **Anti-corruption layer (ACL)** lets an internal bounded context evolve in **its own domain language** while integrating with external systems that have different states, identifiers, units, versions, and protocols. An ACL is not merely renaming fields; it **interprets semantics, verifies trust contexts, resolves references, classifies errors, and blocks external assumptions from leaking into the domain**. At the same time, an ACL never replaces domain invariants, transport security, transactions, idempotency, or durable recovery.

In Spring Integration, an ACL sits cleanly between **inbound adapters/gateways and application-facing `MessageChannel`s**, as well as between **internal commands and outbound adapters/gateways**. File, SFTP, HTTP, JMS, AMQP, Kafka, and JDBC each carry different send/receive mechanics and ACK/offset/transaction semantics; translation protects the domain, yet **only adapter/transport integration tests prove real I/O**, and **end-to-end tests** confirm final business side effects.

A high-quality ACL can answer: **which partner sent the data, which contract version applies, how source/tenant identity was authenticated, which internal object an external ID maps to, what external values mean, which failures must be quarantined, whether events can be redelivered, and what evidence proves the domain processed them accurately**. With clear answers to those questions, a system can onboard new partners, swap providers, or upgrade protocols without corrupting its core business model.

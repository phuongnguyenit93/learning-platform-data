# Normalizer and Message Versioning

In integration systems, multiple producers can send **the same business meaning** using different message structures. An older application sends `orderNo` while a newer one sends `orderId`; one source uses `amountMinorUnits` while another uses `totalMinorUnits`; an earlier event lacks `customerNote` while an upgraded event includes it. If every downstream handler has to know every version, logic gets duplicated and upgrades can break running flows.

**Normalizer** (EIP) solves this by **accepting multiple input representations and converting them into a single canonical representation**. In Spring Integration, a Normalizer is typically **a group of endpoints**—such as a **Router by format/schema version**, followed by a **dedicated Transformer per version**, finally converging on a channel carrying the **canonical message**. Do not assume there is a built-in Spring Integration class or Java DSL `.normalize()` method that automatically understands every schema; version detection, field mapping, validation, and semantics must be designed explicitly.

The lesson **Normalizer and Message Versioning** belongs to the **Normalizer** chapter of the `SPRING_INTEGRATION_PATTERN` module. The module aims to implement Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows—practicing Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, along with testing and monitoring processing branches.

**Core principle:** a version is **part of the data contract**, not a trick to dodge parse errors. The Normalizer must distinguish the **input message's schema version** from the **canonical output schema version**, preserve business identity/idempotency/correlation, transform data with accurate semantics, and **never guess silently** when a version is unsupported.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Explain the Normalizer EIP and why Router + Transformers sit ahead of shared processing flows.
2. Distinguish **wire format**, **message schema version**, **canonical schema version**, **business revision**, **event ID**, and **trace ID**.
3. Recognize risks when multiple producers upgrade at different times.
4. Design `OrderCreatedV1`, `OrderCreatedV2`, and `OrderCreatedCanonical` with explicit semantics.
5. Map renamed fields without accidentally changing units, scale, or meaning.
6. Verify versions from trusted sources and cross-check header vs. payload type.
7. Build a Java DSL Router keyed by `schemaVersion`, each route having its own Transformer.
8. Attach `sourceSchemaVersion` and the new `schemaVersion` for debugging and downstream consumers.
9. Test that v1/v2 converge on the same canonical DTO while unsupported versions never enter business handlers.
10. Distinguish backward/forward compatibility from migration logic inside the Normalizer.
11. Handle unknown/missing versions, inconsistent headers, required fields, and lossy transformations.
12. Preserve event identity, business correlation, and idempotency across version changes.
13. Design rollouts, canaries, schema registry/contract tests, replays, and rollbacks.
14. Monitor message distribution per version, mapping errors, and normalization latency.
15. Combine Normalizer with Filter, Router, Aggregator, retry, and error channels in a reliable flow.

## 2. Why Is Message Versioning an Integration Problem?

Suppose the system receives order events from two producer versions running in parallel:

~~~json
{
  "schemaVersion": "1",
  "eventId": "evt-order-1001",
  "tenantId": "tenant-a",
  "orderNo": "ORDER-101",
  "amountMinorUnits": 250000,
  "currency": "VND"
}
~~~

A newer producer emits:

~~~json
{
  "schemaVersion": "2",
  "eventId": "evt-order-1002",
  "tenantId": "tenant-a",
  "orderId": "ORDER-102",
  "totalMinorUnits": 175000,
  "currency": "VND",
  "customerNote": "Deliver during business hours"
}
~~~

Both messages state that **an order was created**, yet the ID and amount fields are named differently and v2 adds a note. Downstream handlers only need the contract:

~~~text
OrderCreatedCanonical
  eventId
  tenantId
  orderId
  totalMinorUnits
  currency
  customerNote (nullable when absent from source)
~~~

Instead of putting:

~~~java
if (version == 1) {
    // read orderNo
}
else if (version == 2) {
    // read orderId
}
~~~

in dozens of handlers, the Normalizer isolates **version-specific knowledge at the boundary**.

~~~mermaid
flowchart LR
    V1["OrderCreated v1"] --> R{"Version Router"}
    V2["OrderCreated v2"] --> R
    R -->|"1"| T1["Transformer v1→canonical"]
    R -->|"2"| T2["Transformer v2→canonical"]
    T1 --> C["Canonical OrderCreated"]
    T2 --> C
    C --> F["Shared Filter/Router"]
    F --> B["Business handler"]
    R -->|"unsupported"| Q["Quarantine / error outcome"]
~~~

**Meaning of the diagram:** downstream is shielded from structural changes in individual producers. That does **not** mean the canonical contract can change arbitrarily — a new canonical version still needs its own versioning/migration policy and contract tests.

## 3. EIP Normalizer vs. Transformer, Router, and Enricher

Normalizer can be viewed as **a coordination between a Router and Message Translators/Transformers** so multiple input formats converge on a shared representation.

| Component | Problem It Solves | Role in This Lesson |
|---|---|---|
| **Normalizer EIP** | Multiple variants of the same meaning into one standard | Entire v1/v2 → canonical boundary |
| **Content-based Router** | Selects endpoint by property/version | Sends v1 to v1 transformer, v2 to v2 transformer |
| **Header-based Router** | Selects endpoint from metadata | Uses trusted `schemaVersion` header |
| **Transformer** | Converts one representation to another | Maps `orderNo→orderId`, validates money semantics |
| **Content Enricher** | Adds info from another source | Used only when an omitted field is truly needed |
| **Filter** | Accepts/drops messages by condition | Runs eligibility after normalization where appropriate |
| **Aggregator** | Combines multiple messages by group | Requires stable canonical IDs/correlation |
| **Schema validation** | Confirms input conforms to a contract | Enforced at ingress / per version |

A single `.transform(...)` may suffice for two simple versions, yet the Normalizer EIP emphasizes **converging multiple input formats onto one shared contract**, not just renaming a field. Avoid scattering version logic across every business handler.

### 3.1. There Is No Java `normalize` API That Automatically Guesses Schemas

*Normalizer* is a pattern name, not a guarantee that a framework endpoint will magically map arbitrary JSON versions. In Spring Integration Java DSL, you typically compose:

~~~text
IntegrationFlow
  -> .route(...)
  -> v1/v2 channels
  -> .transform(...)
  -> canonical channel
~~~

Or implement a Transformer that dispatches by version in code. Choose based on version count, independence, deployment cadence, and testability.

## 4. Do Not Confuse Different Kinds of “Version”

The word `version` carries many meanings; conflating them creates subtle data bugs.

| Concept | Example | What It Is Used For |
|---|---|---|
| **Wire format version** | JSON vs. Avro; encoding revision | Selecting decoder/serializer |
| **Event type** | `OrderCreated` vs. `OrderCancelled` | Identifying business event kind |
| **Source schema version** | `OrderCreated v1` or `v2` | Selecting transformer |
| **Canonical schema version** | `OrderCreatedCanonical v3` | Internal downstream contract |
| **Business aggregate revision** | `orderRevision=17` | Optimistic concurrency, ordering |
| **Event ID** | `evt-order-1001` | Dedup, audit, at-least-once replay |
| **MessageHeaders.ID** | UUID of a Spring Message | Identifying a message instance |
| **Trace/span ID** | `trace-55` | Distributed flow tracing |
| **API version** | `/api/v2/orders` | HTTP endpoint contract |
| **Application release** | `order-service 4.8.1` | Deployment/build |
| **Schema registry ID** | `subject/id=123` | Looking up schema/decoder in registry |

### 4.1. Schema Version Is Not Business Revision

For example, an order goes through:

~~~text
OrderCreated:   schemaVersion=2, orderRevision=1
OrderPaid:      schemaVersion=2, orderRevision=2
OrderCancelled: schemaVersion=2, orderRevision=3
~~~

Schema version stays constant while business state advances. Conversely, a historical event may be **re-serialized under schema v3** while its business revision remains 1. Using schema version for resequencing or optimistic locking is wrong.

### 4.2. Event ID Must Stay Stable Through Normalization

~~~text
Input v1:
  eventId = evt-order-1001

Canonical output:
  eventId = evt-order-1001
~~~

The Normalizer **must not mint a new event ID** for the same business event just because the payload changed schema. If a broker redelivers a message and the normalizer generates `UUID.randomUUID()` as `eventId`, the downstream Idempotent Receiver can execute side effects twice.

### 4.3. Version Is Not a Correlation ID Either

Three events—Order, Payment, Inventory—may use different schema versions yet share the **same business correlation key** `(tenantId, orderId)`. Grouping by `schemaVersion` causes an Aggregator to merge unrelated v2 orders into one group and split a single order across producer upgrades.

## 5. Three Distinct Transformation Dimensions

### 5.1. Decoding: Bytes → Typed Source DTO

~~~text
Raw JSON bytes
  -> Version-matched JSON/Avro/Protobuf decoder
  -> OrderCreatedV1 or OrderCreatedV2
~~~

The decoder handles syntax, JSON types, schema-required fields, and encoding. If a JSON payload has not been decoded yet, a Transformer expecting `OrderCreatedV1` cannot understand `byte[]` or `String`.

### 5.2. Semantic Normalization: Source DTO → Canonical DTO

~~~text
OrderCreatedV1
  orderNo
  amountMinorUnits

->

OrderCreatedCanonical
  orderId
  totalMinorUnits
~~~

This is not mere renaming: you must verify **the same meaning, the same unit, and the same precision**.

### 5.3. Business Processing After Normalization

~~~text
OrderCreatedCanonical
  -> validate business invariants
  -> Filter / Router / Enricher
  -> downstream business handler
~~~

The Normalizer should not charge payments, write DBs, or mutate order status as an **unintended side effect**. A pure mapper is far easier to retry and test than one that decodes and calls multiple external services.

## 6. Version Policy: Support Matrix

Before writing code, publish which versions the system accepts:

| Input Type | Source Version | Status | Target | Reason |
|---|---|---|---|---|
| OrderCreated | 1 | Supported, legacy | Canonical v3 | Legacy producers still active |
| OrderCreated | 2 | Supported | Canonical v3 | Current producer |
| OrderCreated | 3 | Unsupported input | Quarantine/explicit rejection | No consumer adapter yet |
| PaymentCaptured | 1 | Not OrderCreated | Different event-type Router | Must not be mistaken for OrderCreated v1 |
| OrderCreated | Missing version | Per ingress contract | Reject or published legacy policy | Never guess from field names |
| OrderCreated | Unrecognized | Unsupported version | Error/quarantine | Prevent writing corrupted business data |

**Canonical v3** in this lesson is an **example application convention**, not a Spring Integration framework version. Input v1 and v2 transform directly into canonical v3. That does not mean an external `OrderCreated v3` is supported without its own adapter.

### 6.1. Supporting Legacy Formats vs. Maintaining Backward Compatibility

A consumer can support schema v1 via a dedicated Transformer even when v2 introduces non-backward-compatible changes. **Schema evolution compatibility** and **a normalizer's ability to handle multiple versions** are two different things.

- Schema-compatible: a single decoder/reader handles added/removed fields under format/registry rules.
- Version-specific transformer: maps two incompatible schemas onto the same canonical contract.
- Canonical contract: can still evolve independently with its own rollout rules.

## 7. Backward, Forward, and Full Compatibility

Compatibility terms must be stated in terms of **reader/writer** and serialization format; below is the standard understanding in schema evolution:

| Kind | General Meaning | Example Scenario |
|---|---|---|
| Backward compatibility | New reader can read data written by old writer | New consumer processes v1 events |
| Forward compatibility | Old reader can read data written by new writer | Old consumer ignores new v2 field |
| Full compatibility | Both directions guaranteed by schema rules | Producer/consumer can differ safely in version |
| Breaking change | A reader/writer pair is incompatible | Field type/meaning changed without migration |

**Exact definitions depend on Avro/Protobuf/JSON Schema and registry policies.** Adding a new field is not always compatible if a strict downstream JSON deserializer rejects unknown fields; renaming a field is not automatically compatible just because business meaning stays the same.

### 7.1. Additive Fields Are Not Always Harmless

V2 adds `customerNote`:

- A tolerant consumer ignores unknown fields.
- A strict consumer rejects v2.
- A v1 transformer must not invent `customerNote="N/A"` if business logic treats it as a real customer note.
- If a note is required in canonical, v1 lacks the data to map accurately; define an explicit policy.

### 7.2. Renames Are Not Automatically Compatible

V1 `orderNo` → V2 `orderId` is breaking if an old reader looks only for `orderNo`. The Normalizer explicitly maps both fields instead of updating every downstream handler.

### 7.3. Changing Types or Units Is Riskier Than Renaming

~~~text
v1 amount: integer minor units
v2 amount: decimal major units
~~~

Renaming without converting units shifts amounts by 100x. Define conversion rules with `currency`, scale, rounding, and overflow, and test edge cases. This lesson **keeps both v1 and v2 in minor units** to focus on version routing.

## 8. Example Contract: OrderCreated v1, v2, and Canonical v3

### 8.1. Source Payload v1

~~~java
public record OrderCreatedV1(
        String eventId,
        String tenantId,
        String orderNo,
        long amountMinorUnits,
        String currency
) {}
~~~

### 8.2. Source Payload v2

~~~java
public record OrderCreatedV2(
        String eventId,
        String tenantId,
        String orderId,
        long totalMinorUnits,
        String currency,
        String customerNote
) {}
~~~

### 8.3. Canonical Payload v3

~~~java
public record OrderCreatedCanonical(
        String eventId,
        String tenantId,
        String orderId,
        long totalMinorUnits,
        String currency,
        String customerNote
) {}
~~~

These are **three distinct public top-level Java types**; in a real project, place each record in its own `OrderCreatedV1.java`, `OrderCreatedV2.java`, and `OrderCreatedCanonical.java` file. Java 17+ is required for records.

### 8.4. Field-Level Mapping Table

| Canonical Field | V1 Source | V2 Source | Semantic Rule |
|---|---|---|---|
| `eventId` | `eventId` | `eventId` | Preserve business event identity |
| `tenantId` | `tenantId` | `tenantId` | Verify ownership/tenant at ingress |
| `orderId` | `orderNo` | `orderId` | Never alter business identity |
| `totalMinorUnits` | `amountMinorUnits` | `totalMinorUnits` | Same minor units per currency contract |
| `currency` | `currency` | `currency` | Validate ISO/currency allowlist per domain |
| `customerNote` | Does not exist | `customerNote` | V1 → `null` = not provided; never fabricate data |

**Never default values with financial or authorization significance.** In the demo, v1 lacks `customerNote` so `null` represents *unknown/not provided*. If real v3 requires a non-null note, never fabricate one to fool downstream; update the contract, enrich from a trusted source, or reject with a reason code.

### 8.5. Core Fields That Must Never Be Lost

- `eventId`: used for deduplication.
- `tenantId`: scopes business identity, and must be authenticated.
- `orderId`: correlates with Payment/Inventory.
- `totalMinorUnits` and `currency`: compute exact amounts.
- Version provenance: records which source transformation ran.
- Correlation/trace headers: per transport contract when needed.

Do not confuse a message **normalized into a canonical DTO** with a business event **successfully processed**.

## 9. Normalizer Invariants

Given two source messages expressing the same logical event, the outputs must be semantically equivalent:

~~~text
Normalize(OrderCreatedV1(evt-1001, tenant-a, ORDER-101, 250000, VND))
    ==
Normalize(OrderCreatedV2(evt-1001, tenant-a, ORDER-101, 250000, VND, null))
~~~

Key invariants:

1. **Stable event identity:** `eventId` does not change.
2. **Stable tenant/business key:** `tenantId`/`orderId` stay unchanged.
3. **Preserved money semantics:** amounts/units never change outside contract-approved conversions.
4. **Determinism:** identical input and mapping version → identical canonical payload.
5. **Fail-fast:** unknown versions or missing required fields never map silently.
6. **No hidden business side effects:** normalization never charges, reserves stock, or alters status.
7. **Provenance:** records source version and canonical target version.
8. **No accidental secret propagation:** headers crossing trust boundaries are controlled.
9. **Testable replay:** redelivering an event never turns it into a new event ID.
10. **Explicit lossy rules:** dropped fields or meaningful omissions are documented in the contract.

### 9.1. Normalization Does Not Alter Business Data

If source `totalMinorUnits=250000`, the normalizer must never arbitrarily apply a discount to 240000 and call that “canonical formatting”. Discounts are a separate **business transformation** with their own rules, versioning, and approvals.

### 9.2. Idempotent Transformation vs. Idempotent Receiver

A pure transformer returning identical outputs for identical inputs is **deterministic/idempotent as a mapping**, yet **does not guarantee** downstream side effects run only once. A broker can redeliver both post-normalization copies; an Idempotent Receiver still needs a stable event ID and business uniqueness.

## 10. Version Detection: Header, Envelope, or Registry?

Three common approaches:

| Version Source | Example | Pros | Risks |
|---|---|---|---|
| Message header | `schemaVersion="1"` | Easy for Router to read without touching payload | Header may be missing or spoofed |
| Event envelope | `{"eventType":"OrderCreated","schemaVersion":"1","data":...}` | Explicit contract, easy to audit | Needs decoder to parse envelope first |
| Binary schema/registry ID | Avro/Protobuf registry ID | Enforces codec/schema rules | Needs registry access/cache/version policy |

### 10.1. Headers Must Be Trustworthy

If a client sends:

~~~text
schemaVersion=2
payload=OrderCreatedV1
~~~

a Router relying only on headers could invoke the v2 transformer mistakenly. **Cross-check version against payload type/schema** at the boundary; never let an untrusted header dictate casting alone.

### 10.2. Do Not Guess Version Just Because a New Field Exists

A v1 message might carry an unknown field from an experimental producer toggle; a v2 message might omit an optional field. Inferring `v1` vs. `v2` from the presence of `customerNote` is fragile. Use explicit metadata and schema validation.

### 10.3. Versions Are Not Numbers for Arbitrary Inequality Checks

Do not write `if (version >= 2)` assuming larger versions always contain all old fields. A major version can be breaking. Use a **support matrix** per event type and verified mappings, not integer comparisons alone.
## 11. Java Implementation: An Explicit, Non-Guessing Normalizer

We implement **one bean with two dedicated methods**, `fromV1` and `fromV2`. Each method receives a message, verifies the version metadata against the actual payload, validates, and returns a new `Message<OrderCreatedCanonical>`.

### 11.1. Exception for Invalid Contract/Schema

~~~java
public final class InvalidOrderSchemaException
        extends RuntimeException {

    private final String reasonCode;

    public InvalidOrderSchemaException(String reasonCode) {
        super(reasonCode);
        this.reasonCode = reasonCode;
    }

    public String reasonCode() {
        return reasonCode;
    }
}
~~~

Short, stable reason codes let error flows classify failures cleanly. Never embed raw JSON containing personal data in exception messages.

### 11.2. OrderVersionNormalizer

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class OrderVersionNormalizer {

    public Message<OrderCreatedCanonical> fromV1(
            Message<?> original) {

        requireVersion(original, "1");

        if (!(original.getPayload() instanceof OrderCreatedV1 v1)) {
            throw new InvalidOrderSchemaException(
                    "SCHEMA_VERSION_PAYLOAD_MISMATCH");
        }

        OrderCreatedCanonical normalized =
                new OrderCreatedCanonical(
                        v1.eventId(),
                        v1.tenantId(),
                        v1.orderNo(),
                        v1.amountMinorUnits(),
                        v1.currency(),
                        null);

        return toCanonicalMessage(
                original, normalized, "1");
    }

    public Message<OrderCreatedCanonical> fromV2(
            Message<?> original) {

        requireVersion(original, "2");

        if (!(original.getPayload() instanceof OrderCreatedV2 v2)) {
            throw new InvalidOrderSchemaException(
                    "SCHEMA_VERSION_PAYLOAD_MISMATCH");
        }

        OrderCreatedCanonical normalized =
                new OrderCreatedCanonical(
                        v2.eventId(),
                        v2.tenantId(),
                        v2.orderId(),
                        v2.totalMinorUnits(),
                        v2.currency(),
                        v2.customerNote());

        return toCanonicalMessage(
                original, normalized, "2");
    }

    private void requireVersion(
            Message<?> message,
            String expected) {

        Object actual = message.getHeaders()
                .get("schemaVersion");

        if (!expected.equals(actual)) {
            throw new InvalidOrderSchemaException(
                    "SCHEMA_VERSION_HEADER_MISMATCH");
        }
    }

    private Message<OrderCreatedCanonical> toCanonicalMessage(
            Message<?> original,
            OrderCreatedCanonical normalized,
            String sourceVersion) {

        validateCanonical(normalized);

        MessageBuilder<OrderCreatedCanonical> builder =
                MessageBuilder.withPayload(normalized)
                        .setHeader("schemaVersion", "3")
                        .setHeader(
                                "sourceSchemaVersion",
                                sourceVersion)
                        .setHeader(
                                "eventId",
                                normalized.eventId());

        // Copy only allowlisted metadata at this boundary.
        copyIfPresent(original, builder, "traceId");
        copyIfPresent(
                original, builder, "businessCorrelationId");

        return builder.build();
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

    private static void validateCanonical(
            OrderCreatedCanonical order) {

        if (blank(order.eventId())) {
            throw new InvalidOrderSchemaException(
                    "EVENT_ID_REQUIRED");
        }

        if (blank(order.tenantId())) {
            throw new InvalidOrderSchemaException(
                    "TENANT_ID_REQUIRED");
        }

        if (blank(order.orderId())) {
            throw new InvalidOrderSchemaException(
                    "ORDER_ID_REQUIRED");
        }

        if (order.totalMinorUnits() <= 0) {
            throw new InvalidOrderSchemaException(
                    "INVALID_AMOUNT");
        }

        if (blank(order.currency())
                || !order.currency().matches("[A-Z]{3}")) {
            throw new InvalidOrderSchemaException(
                    "INVALID_CURRENCY_FORMAT");
        }
    }

    private static boolean blank(String value) {
        return value == null || value.isBlank();
    }
}
~~~

**Intentional limitations of the example:**

- `currency.matches("[A-Z]{3}")` checks only the *shape* of the code; it **does not prove** the business supports that currency. Production requires an ISO 4217/domain allowlist and corresponding minor-unit logic.
- `totalMinorUnits > 0` is a rule for positive-amount orders in this example; do not apply it blindly to credit or zero-amount orders if the domain allows them.
- `customerNote=null` when absent in v1 reflects a policy of *never inventing data*. If downstream requires a non-null note, change the contract or enrich from a trusted source.
- `requireVersion` expects a `String` header. If an ingress adapter receives an integer JSON version, normalize it **before the router** rather than coercing inconsistently across endpoints.
- The code does not check authorization of `tenantId` against the principal; that belongs at the adapter/security boundary.
- It avoids copying all message headers, preventing `Authorization`, stale `contentType`, or sensitive contents from propagating. Because `replyChannel` and `errorChannel` are omitted, this example fits **one-way event flows**; request–reply Gateways need header handling matching their contract.

### 11.3. Why Not Use `copyHeaders` Blindly?

A short snippet like:

~~~java
MessageBuilder.withPayload(normalized)
        .copyHeaders(original.getHeaders())
        .setHeader("schemaVersion", "3")
        .build();
~~~

can accidentally carry over:

- `contentType` from raw v1 JSON/Avro even though the payload is now a canonical Java DTO;
- `authorization` or external PII;
- `replyChannel` referencing an object valid only inside the old JVM;
- Conflicting version metadata if not overwritten cleanly;
- Technical headers not allowed across trust boundaries.

Therefore the example uses an **allowlist** of `traceId` and `businessCorrelationId` after confirming they arrive from a trusted channel. Depending on the system, other headers may be added under strict control and testing.

### 11.4. Explicit Version Provenance

A message normalized from v1 looks like:

~~~text
payload:
  OrderCreatedCanonical(
    eventId=evt-order-1001,
    tenantId=tenant-a,
    orderId=ORDER-101,
    totalMinorUnits=250000,
    currency=VND,
    customerNote=null)

headers:
  schemaVersion="3"
  sourceSchemaVersion="1"
  eventId="evt-order-1001"
  traceId="trace-1001"
~~~

Where:

- `schemaVersion` describes the message's **current payload**.
- `sourceSchemaVersion` describes the **source contract** that was mapped.
- `eventId` stays unchanged.
- The v1 note field is `null`, showing the source supplied none.

If you forward `schemaVersion=1` onto the canonical channel, downstream consumers may mistake the payload for v1 and deserialize wrongly. Update the current version after transformation and keep provenance in its own field.

## 12. Spring Integration Java DSL: Router + Two Transformers

Illustrative configuration:

~~~text
orders.in
  -> route by headers['schemaVersion']
       "1" -> orders.v1 -> normalizeV1 -> orders.canonical
       "2" -> orders.v2 -> normalizeV2 -> orders.canonical
       other -> orders.unsupported
~~~

### 12.1. Full Configuration with Separate Channels

~~~java
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
public class VersionAwareNormalizerConfiguration {

    @Bean
    public OrderVersionNormalizer orderVersionNormalizer() {
        return new OrderVersionNormalizer();
    }

    @Bean(name = "orders.in")
    public MessageChannel inbound() {
        return new DirectChannel();
    }

    @Bean(name = "orders.v1")
    public MessageChannel versionOne() {
        return new DirectChannel();
    }

    @Bean(name = "orders.v2")
    public MessageChannel versionTwo() {
        return new DirectChannel();
    }

    @Bean(name = "orders.canonical")
    public PollableChannel canonicalOutput() {
        return new QueueChannel();
    }

    @Bean(name = "orders.unsupported")
    public PollableChannel unsupportedOutput() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow schemaVersionRouter() {
        return IntegrationFlow.from("orders.in")
                .route(
                        "headers['schemaVersion']",
                        router -> router
                                .channelMapping(
                                        "1", "orders.v1")
                                .channelMapping(
                                        "2", "orders.v2")
                                .defaultOutputChannel(
                                        "orders.unsupported"))
                .get();
    }

    @Bean
    public IntegrationFlow normalizerV1Flow(
            OrderVersionNormalizer normalizer) {
        return IntegrationFlow.from("orders.v1")
                .transform(normalizer, "fromV1")
                .channel("orders.canonical")
                .get();
    }

    @Bean
    public IntegrationFlow normalizerV2Flow(
            OrderVersionNormalizer normalizer) {
        return IntegrationFlow.from("orders.v2")
                .transform(normalizer, "fromV2")
                .channel("orders.canonical")
                .get();
    }
}
~~~

**This Java DSL example targets internal event flows**:

- The Router uses an `ExpressionEvaluatingRouter`/SpEL expression to read the header.
- `channelMapping` sends supported versions to dedicated channels.
- `defaultOutputChannel` receives unmapped versions; production needs a **policy-governed error/quarantine handler** rather than letting an unbounded queue grow.
- Both Transformers emit `Message<OrderCreatedCanonical>` onto the canonical output.
- `QueueChannel` is a test fixture collecting output and unsupported inputs. For production, select persistent/broker channels per SLA rather than assuming `QueueChannel` is durable.
- Avoid duplicate endpoint bean names within the same Spring context.
- A Router cannot guarantee correctness if headers are spoofed: `fromV1` and `fromV2` still verify runtime payload types and header versions.

### 12.2. Why Separate Flows Instead of One Long if/else?

Benefits:

1. Each version has its own contract tests.
2. V1 can be deprecated independently once legacy publishers retire.
3. Per-version metrics are easy to observe.
4. V2 mappings stay uncluttered by v1 conditionals.
5. Onboarding v3 follows a clear path: new route, new transformer, new tests.

When version counts are small and mappings concise, a single dispatching Transformer is also valid; what matters is **explicit semantics for every source version**.

### 12.3. When to Use Annotations Instead of Java DSL?

You can annotate a method with `@Transformer(inputChannel="orders.v1", outputChannel="orders.canonical")` on a normalizing bean. Never subscribe both a Java DSL flow and an annotated endpoint to the same input channel expecting every message to visit both: `DirectChannel` uses point-to-point dispatch, not broadcast.

### 12.4. Never Fall Back an Unknown Version to the Nearest One

~~~java
// Anti-pattern: version 5 may be breaking.
String effective = version.equals("1")
        ? "1"
        : "2";
~~~

This sends v3/v4/v5 or malformed headers to the v2 transformer, risking misread data. Unsupported versions must take an **explicit unsupported path** or fail fast—never default to “the latest version”.

## 13. Mapper Unit Tests: V1/V2 Converge on Canonical Semantics

We use `JUnit 5` and `MessageBuilder`. These pure unit tests do not start a Spring Integration context.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class OrderVersionNormalizerTest {

    private final OrderVersionNormalizer normalizer =
            new OrderVersionNormalizer();

    @Test
    void versionOneMapsLegacyNamesAndPreservesIdentity() {
        OrderCreatedV1 event = new OrderCreatedV1(
                "evt-order-1001", "tenant-a",
                "ORDER-101", 250000, "VND");

        Message<OrderCreatedV1> input =
                MessageBuilder.withPayload(event)
                        .setHeader("schemaVersion", "1")
                        .setHeader("traceId", "trace-1001")
                        .build();

        Message<OrderCreatedCanonical> normalized =
                normalizer.fromV1(input);

        assertEquals(
                new OrderCreatedCanonical(
                        "evt-order-1001", "tenant-a",
                        "ORDER-101", 250000, "VND", null),
                normalized.getPayload());

        assertEquals(
                "3", normalized.getHeaders().get("schemaVersion"));
        assertEquals(
                "1", normalized.getHeaders().get("sourceSchemaVersion"));
        assertEquals(
                "trace-1001", normalized.getHeaders().get("traceId"));
    }

    @Test
    void versionTwoMapsCurrentFields() {
        OrderCreatedV2 event = new OrderCreatedV2(
                "evt-order-1002", "tenant-a",
                "ORDER-102", 175000, "VND",
                "Deliver during business hours");

        Message<OrderCreatedCanonical> normalized =
                normalizer.fromV2(
                        MessageBuilder.withPayload(event)
                                .setHeader("schemaVersion", "2")
                                .build());

        assertEquals(
                "ORDER-102", normalized.getPayload().orderId());
        assertEquals(
                175000, normalized.getPayload().totalMinorUnits());
        assertEquals(
                "Deliver during business hours",
                normalized.getPayload().customerNote());
        assertEquals(
                "2", normalized.getHeaders().get("sourceSchemaVersion"));
        assertEquals(
                "3", normalized.getHeaders().get("schemaVersion"));
    }

    @Test
    void sameBusinessEventHasSameCanonicalPayloadInBothVersions() {
        String id = "evt-order-shared";

        OrderCreatedV1 v1 = new OrderCreatedV1(
                id, "tenant-a", "ORDER-900",
                99000, "VND");

        OrderCreatedV2 v2 = new OrderCreatedV2(
                id, "tenant-a", "ORDER-900",
                99000, "VND", null);

        OrderCreatedCanonical canonicalV1 =
                normalizer.fromV1(
                        MessageBuilder.withPayload(v1)
                                .setHeader("schemaVersion", "1")
                                .build())
                        .getPayload();

        OrderCreatedCanonical canonicalV2 =
                normalizer.fromV2(
                        MessageBuilder.withPayload(v2)
                                .setHeader("schemaVersion", "2")
                                .build())
                        .getPayload();

        assertEquals(canonicalV1, canonicalV2);
        assertEquals(id, canonicalV1.eventId());
    }

    @Test
    void wrongVersionHeaderIsRejected() {
        OrderCreatedV1 event = new OrderCreatedV1(
                "evt-order-3", "tenant-a",
                "ORDER-103", 10000, "VND");

        Message<OrderCreatedV1> mismatched =
                MessageBuilder.withPayload(event)
                        .setHeader("schemaVersion", "2")
                        .build();

        InvalidOrderSchemaException error = assertThrows(
                InvalidOrderSchemaException.class,
                () -> normalizer.fromV1(mismatched));

        assertEquals(
                "SCHEMA_VERSION_HEADER_MISMATCH",
                error.reasonCode());
    }

    @Test
    void invalidAmountDoesNotProduceCanonicalEvent() {
        OrderCreatedV2 invalid = new OrderCreatedV2(
                "evt-order-bad", "tenant-a",
                "ORDER-BAD", -1, "VND", null);

        InvalidOrderSchemaException error = assertThrows(
                InvalidOrderSchemaException.class,
                () -> normalizer.fromV2(
                        MessageBuilder.withPayload(invalid)
                                .setHeader("schemaVersion", "2")
                                .build()));

        assertEquals("INVALID_AMOUNT", error.reasonCode());
    }
}
~~~

### 13.1. Equality Tests Alone Do Not Prove Full Schema Compatibility

Testing that two DTOs yield the same canonical payload verifies **mapping of selected values**, not that every schema in the registry is compatible. Add:

- Contract/schema validation tests using real serialized payloads.
- Tests for optional/unknown fields.
- Tests for money units, overflow, and currency rules.
- Tests for null/blank/invalid IDs.
- Tests for serialized envelopes and provenance metadata.
- Tests under the same runtime/framework versions deployed to production.

### 13.2. Metadata Must Not Turn a Source Event into a New Event

In the tests, `eventId` stays unchanged. That is vital when downstream uses `eventId` to deduplicate broker redeliveries. Spring Message `MessageHeaders.ID` can change after transformation; that is **no reason** to generate a new business event ID.

## 14. Integration Test: Two Source Versions, One Canonical Channel

Mapper unit tests cannot catch miswired channels, broken routing expressions, or misplaced transformers. This test boots the real Spring Integration context:

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

@SpringJUnitConfig(classes =
        VersionAwareNormalizerConfiguration.class)
class VersionAwareNormalizerFlowTest {

    @Autowired
    @Qualifier("orders.in")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.canonical")
    PollableChannel canonical;

    @Autowired
    @Qualifier("orders.unsupported")
    PollableChannel unsupported;

    @Test
    void versionOneIsRoutedAndNormalized() {
        OrderCreatedV1 event = new OrderCreatedV1(
                "evt-v1", "tenant-a",
                "ORDER-101", 250000, "VND");

        assertTrue(input.send(
                MessageBuilder.withPayload(event)
                        .setHeader("schemaVersion", "1")
                        .setHeader("traceId", "trace-v1")
                        .build()));

        Message<?> output = canonical.receive(1000);
        assertNotNull(output);
        assertInstanceOf(
                OrderCreatedCanonical.class, output.getPayload());

        OrderCreatedCanonical normalized =
                (OrderCreatedCanonical) output.getPayload();

        assertEquals("evt-v1", normalized.eventId());
        assertEquals("ORDER-101", normalized.orderId());
        assertEquals(250000, normalized.totalMinorUnits());
        assertNull(normalized.customerNote());

        assertEquals(
                "3", output.getHeaders().get("schemaVersion"));
        assertEquals(
                "1", output.getHeaders().get("sourceSchemaVersion"));
        assertEquals(
                "trace-v1", output.getHeaders().get("traceId"));
        assertNull(unsupported.receive(0));
    }

    @Test
    void versionTwoIsRoutedAndNormalized() {
        OrderCreatedV2 event = new OrderCreatedV2(
                "evt-v2", "tenant-a",
                "ORDER-102", 175000, "VND",
                "Deliver during business hours");

        assertTrue(input.send(
                MessageBuilder.withPayload(event)
                        .setHeader("schemaVersion", "2")
                        .build()));

        Message<?> output = canonical.receive(1000);
        assertNotNull(output);
        assertInstanceOf(
                OrderCreatedCanonical.class, output.getPayload());

        OrderCreatedCanonical normalized =
                (OrderCreatedCanonical) output.getPayload();

        assertEquals("ORDER-102", normalized.orderId());
        assertEquals(
                "Deliver during business hours", normalized.customerNote());
        assertEquals(
                "2", output.getHeaders().get("sourceSchemaVersion"));
        assertEquals(
                "3", output.getHeaders().get("schemaVersion"));
        assertNull(unsupported.receive(0));
    }

    @Test
    void unknownVersionIsNotSentToCanonicalHandler() {
        OrderCreatedV2 event = new OrderCreatedV2(
                "evt-unknown", "tenant-a",
                "ORDER-999", 10000, "VND", null);

        assertTrue(input.send(
                MessageBuilder.withPayload(event)
                        .setHeader("schemaVersion", "99")
                        .build()));

        Message<?> rejected = unsupported.receive(1000);
        assertNotNull(rejected);
        assertEquals(event, rejected.getPayload());
        assertNull(canonical.receive(0));
    }
}
~~~

The tests verify:

- Both v1 and v2 inputs produce **canonical DTOs of the same type**.
- Both follow the **matching version route** and converge on `orders.canonical`.
- Current `schemaVersion` updates to `"3"`.
- `sourceSchemaVersion` records whether v1 or v2 arrived.
- Unknown versions never enter the business canonical channel.

### 14.1. Integration Test for Header/Payload Mismatch

Add a test sending an `OrderCreatedV1` with header `schemaVersion="2"`. The Router sends it to `orders.v2`; `fromV2` must reject it because the payload is not `OrderCreatedV2`. With `DirectChannel`, the exception propagates back to the `send()` caller, possibly wrapped by Spring Messaging.

~~~java
@Test
void forgedVersionHeaderIsRejected() {
    OrderCreatedV1 payload = new OrderCreatedV1(
            "evt-mismatch", "tenant-a",
            "ORDER-104", 10000, "VND");

    assertThrows(
            RuntimeException.class,
            () -> input.send(
                MessageBuilder.withPayload(payload)
                        .setHeader("schemaVersion", "2")
                        .build()));

    assertNull(canonical.receive(0));
}
~~~

This snippet is an **additional method inside the test class** above. If you need to assert the reason code, walk the cause chain to locate `InvalidOrderSchemaException` because the framework may wrap it.

### 14.2. Test Isolation

When tests share an `ApplicationContext`, a `QueueChannel` may retain messages left by a prior failed test. Use unique event IDs, drain queues in `@AfterEach`, or isolate contexts. Never run parallel tests against shared named channels without controlling state.

### 14.3. Tests Do Not Yet Cover Real Brokers

The example uses in-memory `DirectChannel`/`QueueChannel`. These tests do not prove:

- JSON payloads decode properly in real adapters.
- Schema registry lookups work.
- Broker retries, offsets, ACKs, or DLQs behave properly.
- Cross-JVM header serialization works.
- Behavior when a producer upgrades mid-consumer restart.

Those require dedicated contract/integration tests against real transports and schema registries.

## 15. Unknown, Missing, and Conflicting Versions

A fault-tolerant system **never defaults an unknown version to v2** and never silently drops auditable messages.

| Input | Recommended Action | Retry the Same Message? |
|---|---|---|
| Version "1" + valid v1 payload | Normalize to canonical | Not needed |
| Version "2" + valid v2 payload | Normalize to canonical | Not needed |
| Unsupported version "9" | Unsupported-version path, alert | No, unless adapter rollout is imminent |
| Missing version | Reject or **published** legacy policy | Usually no if contract requires version |
| Header "2", v1 payload | Reject/contract violation | Never guess |
| Version "2", missing required field | Validation error/quarantine | Never retry endlessly |
| Registry unavailable | Infrastructure failure | Bounded retry/backoff |
| Decoder encounters wrong type | Format/schema error | Never retry verbatim |
| `tenantId` mismatches auth | Security denial | Never bypass by switching version |
| Money unit conversion overflows | Reject, audit | Never clamp silently |

### 15.1. Intentional Fallback vs. Guessing

A legacy producer that genuinely lacks versions can be supported via a **dedicated ingress contract**:

~~~text
legacy-queue-v1 (v1 producers only)
  -> adapter authenticates source
  -> attaches schemaVersion="1"
  -> normalizer
~~~

That is an **explicit policy** tied to a trusted endpoint—distinct from accepting arbitrary external messages lacking versions and guessing from field names.

### 15.2. Never Coerce `"2.0"` or Integer `2` to `"2"` Inconsistently

If the contract specifies String `"2"`, pick one **adapter normalization** point to convert accepted representations, or reject. Never let the Router expect `"2"` while a Transformer accepts integer `2` differently: a message could route successfully and fail validation, or vice versa.

### 15.3. Unsupported Channels Need Bounded Capacity

`orders.unsupported` in the example is a `QueueChannel` for testing. In production, the queue needs bounded capacity, retention/expiry, and a consumer/quarantine flow. Otherwise, sustained unknown versions can exhaust memory.

An unsupported message record should carry **version, event type, producer ID, reason code, and policy-compliant event identifier**, without dumping full PII into logs.

## 16. Normalizer and Content-Based Router/Filter

If a Filter/Router sits **before the Normalizer** and reads version-specific fields directly:

~~~java
// This code cannot run on OrderCreatedV1.
boolean eligible(OrderCreatedV2 v2) {
    return v2.totalMinorUnits() > 100000;
}
~~~

it fails on v1 payloads. Typically:

~~~text
Version-aware decoding
  -> Normalizer
  -> Canonical validation
  -> Business eligibility Filter
  -> Downstream Router
~~~

### 16.1. Cases Requiring a Filter Before the Normalizer

You may want to block malformed messages, oversized payloads, or unauthorized tenants **before** deserializing and normalizing. That is **security/ingress validation** — not a business Filter depending on canonical fields.

Examples:

- Raw input size limits.
- Source and tenant authentication.
- Allowing only registered event types.
- Checking magic bytes or format markers.
- Rejecting `schemaVersion` outside an allowlist.

Afterward, the Normalizer maps valid source payloads onto the shared contract.

### 16.2. Same Business Rule Across Two Representations?

Instead of writing two `Filter`s for v1 and v2, normalize both to canonical and run **one Filter**. However, if v1 lacks a field required by the Filter, never fabricate it; apply an explicit legacy rule, trusted enrichment, or reject that message type per business contract.

## 17. Correlation and Aggregator When Source Versions Mix

An order may be created with schema v1, `PaymentCaptured` emitted with v2, and `InventoryReserved` emitted with v3. The Aggregator must group by **business group identity**, such as `(tenantId, orderId)` — never by `schemaVersion`.

~~~mermaid
flowchart LR
    O1["OrderCreated v1"] --> N1["Order Normalizer"]
    P2["PaymentCaptured v2"] --> N2["Payment Normalizer"]
    I3["InventoryReserved v3"] --> N3["Inventory Normalizer"]
    N1 --> A["Aggregator by tenantId+orderId"]
    N2 --> A
    N3 --> A
    A --> OUT["OrderReady"]
~~~

### 17.1. Never Use Source Version as a Correlation Key

~~~text
Group(schemaVersion=1):
  OrderCreated for 100 orders

Group(schemaVersion=2):
  PaymentCaptured for 100 orders
~~~

This dangerously **mixes unrelated workflows**. Version selects decoders/transformers, whereas correlation keys identify **messages belonging to the same business unit**.

### 17.2. Normalization Must Keep IDs Stable

If v1 `orderNo="ORDER-101"` and v2 `orderId="ORDER-101"` refer to the same order, canonical `orderId` must match. Never normalize by generating a new order ID from random values, timestamps, or emails. If external IDs must map to canonical internal IDs, apply a trusted mapping before aggregation and test key consistency.

### 17.3. Sequence Metadata Is Not Schema Version

Splitters attach `sequenceNumber` and `sequenceSize` by part count; those are not schema versions. The Normalizer must never replace sequence headers or `correlationId` with source schema version. When Transformers build new Messages, retain required headers per contract so downstream Resequencers/Aggregators keep working.

## 18. Idempotent Receiver and Replay Across Normalizer Upgrades

An event may be redelivered by a broker after producers or consumers upgrade.

~~~text
First delivery:
  OrderCreatedV1(eventId=evt-1001)
  -> Canonical v3
  -> Business action

Redelivery:
  OrderCreatedV1(eventId=evt-1001)
  -> Canonical v3
  -> Idempotent receiver skips already applied event
~~~

**Never mint a new `eventId` in the normalizer.** If a consumer hashes serialized canonical JSON as a deduplication key, mapping or source-version changes can yield a different key for the same business event. Use a stable `(tenantId, sourceId, eventId, operationType)` plus a business content fingerprint contract.

### 18.1. Same Event ID, Changed Source Schema

An event may be republished under schema v2 while retaining its business event ID. Then:

- The Normalizer should yield a canonical result with identical meaning.
- The Idempotent Receiver must recognize it as **the same event** and skip re-applying side effects.
- If the same event ID arrives with a different amount, trigger **conflict/reconciliation** rather than silently skipping.
- You can store a canonical business fingerprint and target canonical schema version for auditing.

### 18.2. Never Equate Pure Mapping with Exactly-Once

The Normalizer does not handle broker redeliveries, local/remote transactions, or ACKs on its own. Even with deterministic mapping, downstream side effects can still run twice without idempotency.

## 19. Versioned Normalization and Error Handling

A Normalizer can fail in distinct ways:

| Error | Example | Handling |
|---|---|---|
| Unsupported source version | Unsupported "9" | Quarantine/reject explicitly; never pretend another version |
| Payload/header mismatch | Header 2, v1 object | Non-retryable validation error |
| Missing required ID | Blank `eventId` | Non-retryable contract failure |
| Unit conversion failure | Integer overflow | Reject; never round silently |
| Schema registry outage | Cannot fetch schema | Bounded retry |
| Mapping service timeout | Cannot resolve external ID | Retry or reconcile per SLA |
| Authorization failure | Tenant mismatches principal | Deny/audit |
| Programming defect | Unchecked `ClassCastException` | Alert, rollback, fix |
| Downstream business failure | DB/transient external API | Dedicated error flow, idempotent retry |

### 19.1. DirectChannel vs. Async Channels

In `VersionAwareNormalizerConfiguration`, routes and transformers run over `DirectChannel`. Exceptions from Transformers bubble back to the `send()` caller (possibly wrapped in `MessagingException`).

With `ExecutorChannel`, pollers, or broker listeners, errors occur on another thread and can be routed by error handlers as `ErrorMessage`s to a configured error channel. Never assume synchronous exceptions automatically reach the global `errorChannel`.

### 19.2. Unsupported Version Differs from Normal Filter Discard

A version outside the support matrix usually indicates a **contract or rollout issue**, not an expected business skip. Dropping it silently lets producers emit thousands of unprocessed events unnoticed. Quarantine with `UNSUPPORTED_SCHEMA_VERSION` and alert per producer and event type.

### 19.3. Never Retry Deterministic Errors Indefinitely

If v2 transformation always fails due to a missing required field, retrying the exact same payload will never fix the schema. Use non-retryable rejection/DLQ and notify the producer. Retry only transient failures like unavailable registries or databases, with bounded attempts and backoff.
## 20. Zero-Downtime Multi-Version Rollouts

Normalizer shines when producers and consumers **cannot deploy simultaneously**. A safe rollout follows **expand → migrate → contract**.

~~~mermaid
flowchart TD
    A["T0: Reader supports v1"] --> B["T1: Deploy reader supporting v1 and v2"]
    B --> C["T2: Contract tests and observability"]
    C --> D["T3: Producer begins emitting v2"]
    D --> E["T4: Monitor v1/v2 backlog"]
    E --> F["T5: Producer stops emitting v1"]
    F --> G["T6: v1 replay window expires, remove adapter"]
~~~

Steps:

1. **Expand consumer first:** ensure consumers read both v1 and v2 before producers emit v2.
2. **Contract test:** send real serialized messages for every source version.
3. **Canary v2 writer:** enable on a fraction of traffic where appropriate.
4. **Observe:** source version share, mapping errors, and consumer lag.
5. **Retire v1 producer:** yet keep the v1 reader active while backlogs remain.
6. **Check DLQ/history:** remove the v1 converter only after the replay window expires.
7. **Rollback plan:** if producers must revert to v1, consumers can still read it.

### 20.1. Why Can't the V1 Normalizer Be Deleted Immediately?

V1 messages can remain in brokers, DLQs, or event archives even after producers upgrade. Removing the v1 adapter too early breaks **historical data reprocessing**.

| Condition Before Deprecating | What to Verify |
|---|---|
| No live v1 writers remain | Inventory and metrics |
| Broker v1 backlog is empty | Consumer lag/queues |
| V1 DLQ items resolved or migrated | DLQ report |
| V1 historical replay expired or alternate reader exists | Retention policy |
| Rollback no longer needs v1 | Deployment runbook |
| Late v1 arrivals have clear outcomes | Reject/quarantine contract |

### 20.2. Shadow Normalization

You can mirror a **read-only/comparison** copy to a shadow converter to verify mappings, provided the shadow branch **never writes to business DBs or calls payment APIs**. If comparing outputs via hashes, define canonical field ordering and access controls carefully; avoid logging personal data.

## 21. Schema Registry and Serialization

With Avro/Protobuf/JSON Schema, pipelines typically look like:

~~~text
Wire bytes + schema metadata
  -> Deserialize with matching schema/reader
  -> OrderCreatedV1 / OrderCreatedV2
  -> Version-aware Normalizer
  -> OrderCreatedCanonical
~~~

### 21.1. Schema Registry ID Is Not Source Schema Version

A registry ID identifies a concrete schema in the registry, whereas subject versions track evolution history. Never treat `schemaId=123` as `schemaVersion="123"` or use arithmetic comparisons to select converters.

### 21.2. Decoder and Normalizer Have Different Responsibilities

A method `fromV1(Message<?>)` expects a payload already decoded as `OrderCreatedV1`; it does not decode raw `byte[]` or JSON Strings. The decoder validates syntax/schema first, and then the Router and transformer perform semantic mapping.

### 21.3. Compatible Schema Does Not Guarantee Valid Business Meaning

A change can pass schema compatibility checks yet still break business semantics:

- Changing amount from **major** to **minor units** without renaming the field.
- A status field gaining a new meaning.
- A default that is wrong for historical events.
- Old enum values interpreted differently.
- A syntactically optional field that business handlers actually require.

You need both **schema validation** and **semantic normalization tests**.

### 21.4. Changing Canonical Version Is a Separate Migration

~~~text
Source v1 -> Canonical v3
Source v2 -> Canonical v3

Later:
Source v1 -> Canonical v4
Source v2 -> Canonical v4
Source v3 -> Canonical v4
~~~

When canonical v3 advances to v4, **every converter and downstream consumer** may need updating. Supporting multiple source versions does not guarantee compatibility across canonical contract upgrades.

## 22. Lossy Transformations and Insufficient Information

A Normalizer cannot always transform losslessly.

| Field Kind | Example | Rule |
|---|---|---|
| Required across all versions | `eventId`, `orderId` | Validate; reject if missing |
| Optional | `customerNote` | Use null/optional per contract |
| Renamed | `orderNo` → `orderId` | Map identity accurately |
| Unit-converted | major → minor amount | Convert with scale/rounding |
| Deprecated | legacy displayName | Never use in place of business ID |
| Security-sensitive | accessToken/PII | Never copy arbitrarily |
| Technical metadata | `contentType`/`schemaVersion` | Update to reflect output format |

### 22.1. Never Invent Business Defaults

If source v1 lacks `customerNote`, never inject `"Customer requested early delivery"` just to pass validation. In the example, v1 maps to `null`, preserving “not provided”.

If canonical strictly requires a field that a source omits, you can:

1. Update the canonical contract to represent unknown.
2. Enrich from a trusted source if business rules permit.
3. Backfill/migrate data.
4. Reject with reason `UNMAPPABLE_REQUIRED_FIELD`.

### 22.2. Money Semantics and Overflow

The lesson uses **minor units** in both v1 and v2. If a real schema sends decimal major units, conversion must respect currency scale and check overflow rather than casting floats carelessly:

~~~java
// Anti-pattern: double has rounding error, currency scales differ.
long minor = (long) (majorAsDouble * 100);
~~~

USD normally uses 2 decimal places; JPY and VND do not match USD. Never multiply every currency by 100. That is a **semantic** concern requiring boundary, rounding, and overflow tests per contract.

### 22.3. Records and Mutable Nested Payloads

A Java record holding `String` and `long` is a clean illustration. Yet a record containing `byte[]`, `Map`, or a mutable list does not provide deep immutability automatically. When persisting or fanning out across handlers, use defensive copies/snapshots.

## 23. Security and Version/Header Provenance

**A version header is not proof of permission to emit events.** A client sending `schemaVersion=2` can still send bad payloads or an unauthorized tenant.

At ingress:

- Authenticate the source and verify the tenant.
- Verify event type and schema/serializer metadata.
- Cross-check header and payload versions.
- Enforce authorization before side effects.
- Enforce replay/idempotency protections.
- Never log raw payloads, `Authorization`, or access tokens.

### 23.1. Header Allowlist

Example input:

~~~text
headers:
  schemaVersion=1
  contentType=application/legacy-order-json
  Authorization=Bearer SECRET
  traceId=trace-1001
  businessCorrelationId=ORDER-101
~~~

Once the payload becomes a canonical Java DTO, the original `contentType` may no longer apply, and `Authorization` must never propagate across channels. Section 11's normalizer keeps only **selected headers**, updating current version and source provenance.

In request–reply Gateways, headers like `replyChannel`/`errorChannel` require separate handling. Never forward internal channel objects blindly across cross-JVM brokers.

### 23.2. Unsupported Does Not Mean Unsafe to Discard

When receiving an unknown version, emit minimal logs:

~~~text
flow=order-normalizer
eventType=OrderCreated
sourceSchemaVersion=9
producer=order-service
outcome=REJECTED_UNSUPPORTED
reasonCode=UNSUPPORTED_SCHEMA_VERSION
traceId=trace-2001
~~~

Quarantining raw payloads (if required) needs encryption, retention, access controls, and proper redaction. Error messages embedding full PII-laden JSON must never appear on public dashboards.

## 24. Performance, Backpressure, and Durability

Costs inside a Normalizer can arise from:

- Deserializing large payloads.
- Repeated schema registry lookups.
- Looking up external business IDs over the network.
- Complex validation/transformation.
- Copying large headers/collections.
- Growing backlogs on the unsupported queue.
- Slow downstream canonical consumers.

Design guidelines:

1. Cache schema lookups with version controls.
2. Keep converters pure; avoid unnecessary remote calls.
3. Enforce bounded queues and backpressure/rate limiting.
4. Encode canonical DTOs at the right outbound boundary.
5. Give unsupported/quarantine flows bounded capacity, expiry, and consumers.
6. Track latency metrics by source schema version.
7. When parallelizing, preserve business ordering/correlation explicitly.

### 24.1. Schema Version Is Not an Ordering Key

If v1 and v2 execute on different executors, outputs can finish out of arrival order. Never sort messages by `schemaVersion`, which is a *format* version. When business order matters, use `aggregateRevision`, `sequenceNumber`, and proper correlation.

### 24.2. Retries and Durability

The demo's `DirectChannel`/`QueueChannel` provide no durability across restarts. Production requires persistent brokers/storage and transactional ACKs if messages must not be lost. A deterministic Normalizer enables safe replay, yet never replaces downstream idempotency.

## 25. Observability for Multi-Version Migrations

| Metric | Meaning | Recommended Labels |
|---|---|---|
| `normalizer_received_total` | Inputs by source version | `eventType`, `version` |
| `normalizer_success_total` | Successful normalizations | `source`, `canonicalVersion` |
| `normalizer_unsupported_total` | Unsupported versions | `producer`, `sourceVersion` |
| `normalizer_schema_mismatch_total` | Header/payload mismatches | `version`, `reason` |
| `normalizer_invalid_payload_total` | Contract-violating fields | `reasonCode` |
| `normalizer_latency_seconds` | Transformation duration | `sourceVersion` |
| `normalizer_output_total` | Canonical messages emitted | `canonicalVersion` |
| `normalizer_quarantine_total` | Messages needing repair | `reason` |
| `normalizer_replay_total` | Replayed messages | `eventType` |
| `normalizer_downstream_error_total` | Post-normalization failures | `outcome` |

Alert when:

- A new version arrives before consumers support it.
- `SCHEMA_VERSION_PAYLOAD_MISMATCH` spikes after a decoder update.
- V1 and v2 stop converging on the same business example.
- Event IDs change during normalization, breaking deduplication.
- V1 backlog remains high just before removing the legacy adapter.
- The unsupported queue nears capacity.

Never use `eventId`, `orderId`, `customerId`, or `traceId` as **unbounded-cardinality metric labels**. Keep them inside access-controlled logs/traces, redacted or hashed per policy.

## 26. Common Anti-Patterns

| Mistake | Consequence | Fix |
|---|---|---|
| Omitting source schema version | Guessing from field names | Trusted version envelope/header |
| Header says v2, payload is v1 | Wrong casts, data corruption | Validate type/schema |
| Defaulting unknown version to v2 | Breaking schemas misread | Explicit unsupported path |
| Canonical v3 payload with `schemaVersion=1` header | Downstream decodes wrongly | Set target version + source provenance |
| Conflating app release with schema version | Deployments alter routing | Separate contract versions |
| Using order revision as source version | Business updates route differently | Keep concepts distinct |
| Minting new `eventId` in transform | Replays execute duplicates | Preserve stable event ID |
| Using `schemaVersion` as correlation key | Groups merged or split wrongly | Use business key |
| Fabricating required fields missing in v1 | Corrupted data | Optional/enrich/reject |
| Converting amounts with `double` | Monetary drift | Minor units/`BigDecimal` |
| Copying all headers | Leaks secrets/stale `contentType` | Allowlist |
| Reader has v2 decoder but no mapper | Fails to reach canonical | End-to-end tests |
| Writer emits v2 before reader supports it | Unsupported events | Expand consumer first |
| Deleting v1 converter too early | Historical DLQ/replays fail | Retention-aware removal |
| Testing only v2 happy paths | Misses schema drift | Version matrix |
| Silently dropping unknown versions | Lost business events | Quarantine, audit, alert |
| Assuming Normalizer deduplicates | Replays duplicate side effects | Idempotent Receiver |
| Remote lookups inside every transformer | Latency and state drift | Trusted mapping at ingress |
| Upgrading canonical v4 without migrating consumers | Downstream breaks | Canonical rollout |

## 27. Hands-On Practice, Exercises, and Test Matrix

**Exercise 1 — Two schemas:** identify renamed and optional fields between `OrderCreatedV1` and `OrderCreatedV2`.

**Exercise 2 — Pure mapper:** run `OrderVersionNormalizerTest`, verifying v1/v2 map to the same canonical DTO with `eventId` unchanged.

**Exercise 3 — Version router:** run `VersionAwareNormalizerFlowTest`, verifying both source versions reach the canonical channel.

**Exercise 4 — Unknown version:** send header `"9"` and verify no canonical output appears while the unsupported channel receives the message.

**Exercise 5 — Header mismatch:** attach version `"2"` to a v1 DTO and test for non-retryable contract failure.

**Exercise 6 — Missing version:** design explicit policies for a trusted legacy queue vs. unversioned public ingress.

**Exercise 7 — Invalid IDs:** pass blank `eventId` or `orderId`, expecting an exception with a `reasonCode`.

**Exercise 8 — Optional note:** v1 maps note to `null`; v2 preserves the provided note. Never invent defaults.

**Exercise 9 — Currency conversion:** suppose a v3 source sends decimal major units; design a converter respecting currency scale/rounding and test USD/VND.

**Exercise 10 — Idempotency:** send the same `eventId` twice with different `MessageHeaders.ID`s; ensure downstream side effects execute once.

**Exercise 11 — Aggregator:** mix source versions across Order, Payment, and Inventory events while grouping by `tenantId`/`orderId`.

**Exercise 12 — V1 replay:** after producer upgrades, replay a v1 event from the DLQ; prove the reader still supports it.

**Exercise 13 — Schema registry:** test unavailable registry vs. unknown schema ID, separating retryable from non-retryable.

**Exercise 14 — Security:** reject payloads whose `tenantId` differs from the authenticated tenant before any business flow.

**Exercise 15 — Header allowlist:** include `Authorization` and stale `contentType` on input; verify canonical output drops secrets and retains valid `traceId`.

**Exercise 16 — Performance:** measure per-version transformer latency and unsupported queue backlog.

### Minimum Test Matrix

| Input | Expected |
|---|---|
| Valid v1 | Canonical v3, proper rename, null note |
| Valid v2 | Canonical v3, note preserved |
| V1/V2 for same logical event | Equivalent canonical payload |
| Unsupported version | Explicit unsupported outcome |
| Header v2, v1 DTO | Rejected, no business side effect |
| Missing version | Rejected or explicit trusted legacy policy |
| Missing `eventId` | Validation error |
| Negative amount | Validation error; never auto-fix blindly |
| Invalid currency | Validation error |
| Unauthorized tenant | Security denial |
| Duplicate delivery | Stable `eventId`, downstream idempotent |
| V1 replay after upgrade | Readable or documented migration |
| Registry unavailable | Bounded retry; never dropped as invalid |
| Two orders with same version | Never grouped together |
| Header with secret | Never crosses canonical boundary |

### Self-Check Questions

1. Which endpoint types commonly compose the Normalizer EIP?
2. Why is a single Transformer often insufficient for multi-version inputs?
3. How do source schema version and canonical schema version differ?
4. Should business revision be used to route schemas?
5. Why must `eventId` stay unchanged through normalization?
6. Is a client-supplied version header completely trustworthy?
7. Why not default unknown versions to the newest adapter?
8. When can v1 and v2 map to the same canonical DTO?
9. What should happen when a source omits an optional note?
10. How does a field rename differ from a unit change?
11. How do backward and forward compatibility relate to readers and writers?
12. Can a schema-compatible change still violate business meaning?
13. Why must readers expand before writers upgrade?
14. When is it safe to remove a legacy normalizer?
15. How do DLQ replays affect adapter deprecation?
16. Does a Normalizer guarantee exactly-once processing on its own?
17. How does `schemaVersion`'s role differ from `correlationId`'s?
18. What risks arise when placing a Filter ahead of a Normalizer?
19. What bugs can a stale `contentType` cause?
20. Is a registry ID always equal to a version number?
21. Which metrics prove v1 traffic has drained?
22. Which test catches mismatches between version headers and payload types?

## 28. Design Checklist

- [ ] Defined event type, supported source versions, and canonical target version.
- [ ] Separated wire format/schema version from business revision and event ID.
- [ ] Obtained version metadata from authenticated sources.
- [ ] Defined a support matrix for unknown and missing versions.
- [ ] Cross-checked version headers against runtime payload types/schemas.
- [ ] Built separate mappings, validations, and tests per version.
- [ ] Standardized outputs onto one canonical contract so downstream never casts source DTOs.
- [ ] Updated current `schemaVersion` properly while preserving source provenance.
- [ ] Kept business `eventId` and `tenantId`/`orderId` free of random regeneration.
- [ ] Defined money/currency/units/rounding/overflow rules.
- [ ] Avoided fabricating defaults for critical business fields.
- [ ] Documented semantics for optional, required, and deprecated fields.
- [ ] Used a header allowlist blocking `Authorization`, PII, and stale `contentType`.
- [ ] Enforced authentication/tenant authorization before business side effects.
- [ ] Routed unknown versions to explicit quarantine/errors, never silent drops.
- [ ] Applied bounded retries for transient registry/network failures.
- [ ] Configured capacity, retention, consumers, and alerts on unsupported queues.
- [ ] Maintained serialized v1/v2 samples for contract tests.
- [ ] Built JUnit mapper tests and channel-level integration tests.
- [ ] Tested null/blank IDs, amounts, currencies, missing versions, and mismatches.
- [ ] Tested canonical equality across two versions of the same logical event.
- [ ] Enforced downstream idempotency for redeliveries.
- [ ] Configured Aggregators/Resequencers to use business correlation/sequence, never source version.
- [ ] Planned separate rollouts for canonical evolution.
- [ ] Expanded readers before upgrading writers.
- [ ] Scheduled v1 converter removal only after backlog/DLQ/replay windows clear.
- [ ] Instrumented metrics by `eventType`/`sourceVersion`/`canonicalVersion`/`reason`.
- [ ] Excluded high-cardinality event/order/trace IDs from metric labels.
- [ ] Assigned owners and contract docs for every schema and adapter.

## 29. Summary

**Normalizer and message versioning** solves the challenge of converging **multiple representation versions of the same business domain** onto **one canonical contract**. In Spring Integration, a clean design pairs a Router over verified versions, dedicated Transformers per source schema, and one canonical channel so downstream never branches on v1 vs. v2.

Keep source schema version (for decoders/transformers), canonical version (for the internal contract), business revision (for ordering/state), and `eventId` (for idempotency) distinct. Never use version as a correlation key, and never mint new business IDs during normalization. When changing field names, types, or units, preserve **meaning** rather than merely satisfying compilation.

For reliable upgrades in **SPRING_INTEGRATION_PATTERN**, follow **expand consumer → migrate producer → drain old data → remove old adapter**, enforce clear policies for unknown/missing versions, protect headers, test replays, and monitor version distribution. A sound Normalizer keeps Router, Filter, Transformer, Aggregator, Gateway, retry, and error channels working smoothly across upgrades without losing business events or misinterpreting data.

### References

- Enterprise Integration Patterns — Normalizer: https://www.enterpriseintegrationpatterns.com/patterns/messaging/Normalizer.html
- Spring Integration Reference — Router: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference — Transformer: https://docs.spring.io/spring-integration/reference/transformer.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration Reference — Message Channels: https://docs.spring.io/spring-integration/reference/channel.html
- Spring Integration Reference — Error Handling: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference — Aggregator: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference — Resequencer: https://docs.spring.io/spring-integration/reference/resequencer.html
- Spring Integration Reference — Message Store: https://docs.spring.io/spring-integration/reference/message-store.html
- Apache Avro Specification: https://avro.apache.org/docs/current/specification/
- Protocol Buffers — Proto3 Guide: https://protobuf.dev/programming-guides/proto3/
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/

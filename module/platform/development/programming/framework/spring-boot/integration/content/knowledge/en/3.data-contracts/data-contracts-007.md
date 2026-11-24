# Contract Versioning and Compatibility When Adding or Removing Fields

## Objectives and Context

In the **SPRING_BOOT_INTEGRATION** module, Spring Boot orchestrates system integration across HTTP clients, databases, caches, message brokers, and Spring Integration adapters. A single service may receive HTTP JSON, call partner REST/SOAP endpoints, persist to PostgreSQL, publish events to Kafka/RabbitMQ, and cache results in Redis. When an application changes a data contract, **participants cannot upgrade simultaneously**: one pod may still run the old release, a consumer may be reading week-old backlog events, a partner may not have updated its SDK, an outbox row may still wait for publishing, or a DLQ may await replay.

Scenario: the first version of `OrderConfirmed` carried only `orderId` and `amount`; a later version adds `currency` and removes `customerName`. A producer author might assume editing a Java record and deploying suffices. Yet when an old consumer rejects unknown fields, a new consumer defaults `currency="USD"` while historical records were actually VND, or an old event in the DLQ gets replayed, the integration fails or **silently corrupts business logic** even though JSON still parses.

This lesson in the **Data Contracts** chapter covers **contract versioning and compatibility when adding or removing fields**. The focus is on evaluating compatibility from a **concrete reader/writer perspective**, defining absent/null/default semantics, evolving requests/responses/events as well as XML/Avro/Protobuf, planning multi-version rollouts, writing contract tests, and managing change risks.

### After This Lesson, You Will Be Able To

1. Distinguish schemas, semantic contracts, versions, producers/writers, and consumers/readers.
2. Explain **backward, forward, and full compatibility**, including transitive variants and how naming conventions differ across systems.
3. Analyze the impact of adding, removing, renaming, changing types, adding enum values, or altering required/null/default rules.
4. Write explicit Java DTOs and Jackson contracts without silently assuming every client ignores unknown fields.
5. Design an **expand → migrate → contract** plan to retire fields without breaking older consumers.
6. Choose policies for REST/OpenAPI, SOAP/XML/XSD, Kafka/RabbitMQ, and Schema Registry.
7. Separate schema versions from event identities, business versions, and API deployment versions.
8. Test old–new producers, old–new consumers, backlog events in brokers/DLQs, databases, and caches together.
9. Catch incompatible changes pre-deploy, instrument telemetry for deprecation windows, and plan rollbacks.
10. Apply these practices to a realistic Spring Boot flow with outbox, idempotency, and retries.

> **Rule:** A change is *compatible* only when **actively running readers** can read data from **actively running writers** while preserving **exact business meaning**. "Valid JSON" is not enough.

## 1. What Does a Data Contract Include?

A contract is more than field names and types. It spans multiple layers:

| Component | Example | Risk when changed |
| --- | --- | --- |
| Field names & structure | `orderId`, `customer.id` | Readers fail to locate paths |
| Data types | string → number, int32 → int64 | Parse errors, overflows, precision loss |
| Required/optional/nullability | `currency` becomes required | Historical payloads lack the field |
| Defaults | Missing `currency` → "VND" | Wrong assumption for international orders |
| Enums & unknown values | `PENDING`, `CONFIRMED` | Exhaustive switches fail |
| Values, units, formats | minor units, ISO-4217 | Wrong monetary calculations |
| Business invariants | `quantity > 0`, state transitions | Illegal domain data accepted |
| Identity & correlation | `eventId`, `operationId` | Retries produce duplicate side effects |
| Ordering/causality | `aggregateVersion` | Stale events overwrite newer state |
| Error semantics | HTTP 409, field-level errors | Clients retry inappropriately |
| Transport/envelope | Content-Type, headers, topic/routing key | Messages routed or deserialized wrongly |
| Retention & replay | 30-day topic, 90-day DLQ | New readers must decode very old records |
| Security/privacy | PII/secrets/classifiers | Logging or exposing restricted fields |

Two payloads with identical schemas where one side switches `amount` from major units to minor units are **semantically incompatible**—far more dangerous than a clean parse error.

### 1.1. Do Not Confuse Four Kinds of Versions

~~~mermaid
flowchart TD
    A["SPRING_BOOT_INTEGRATION deployment"] --> B["Application version: 2.7.0"]
    A --> C["HTTP API contract version: v2"]
    A --> D["Event schemaVersion: 3"]
    A --> E["Aggregate business version: 42"]
    A --> F["Database migration: V18"]
~~~

- **Application version**: release/build version of the service binary.
- **API contract version**: public contract of an endpoint/method or media type.
- **Event schema version**: how serialized event payloads are decoded.
- **Aggregate version**: sequential mutation counter on an order for optimistic locking and stale-event defense.
- **Database migration version**: ordering of DDL/data migrations.

Never use `aggregateVersion=42` to pick schema v42 for parsing, and never equate a container image tag with an API major version.

### 1.2. Who Are the Writer and Reader?

For a single message:

~~~text
Producer/Writer: Order Service → serializes JSON event
Consumer/Reader: Inventory Service → deserializes JSON event
~~~

For an HTTP exchange there are **two directions**:

~~~text
HTTP request:  Caller writer → Server reader
HTTP response: Server writer → Caller reader
~~~

A server change that "accepts old requests" may be safe on the request side while "adding a response field" breaks old strict callers. Always evaluate **each direction separately**.

## 2. Backward, Forward, and Full Compatibility

### 2.1. Exact Definitions by Reader/Writer

Let:

- `W1`: writer producing schema v1 payloads.
- `W2`: writer producing schema v2 payloads.
- `R1`: reader understanding schema v1.
- `R2`: reader understanding schema v2.

A widely used convention (such as Schema Registry in streaming ecosystems):

- **Backward compatibility:** `R2` can read older data produced by `W1`.
- **Forward compatibility:** `R1` can read newer data produced by `W2`.
- **Full compatibility:** both directions above hold.

~~~mermaid
flowchart LR
    W1["Writer v1"] -->|"BACKWARD"| R2["Reader v2"]
    W2["Writer v2"] -->|"FORWARD"| R1["Reader v1"]
    W1 -. "FULL" .-> R2
    W2 -. "FULL" .-> R1
~~~

**Terminology note:** Some teams use "backward compatible" informally to mean "old clients still work," closer to `R1 ← W2`. To avoid confusion, always specify the exact **reader/writer pair** in docs and test matrices.

### 2.2. Compatibility Matrix Table

| Reader | Writer | Meaning |
| --- | --- | --- |
| `R1` | `W1` | Baseline system |
| `R2` | `W1` | New reader handles old payloads: backward |
| `R1` | `W2` | Old reader handles new payloads: forward |
| `R2` | `W2` | Upgraded system |
| `R3` | `W1` | Supports two versions back: **transitive** within promised window |
| `R1` | `W3` | Very old client reads much newer data: requires long-lived contract support |

Testing only `R2 × W2` proves nothing about zero-downtime upgrades.

### 2.3. Transitive vs. Non-Transitive

Suppose a system evolves `v1 → v2 → v3 → v4`:

- Non-transitive backward typically checks the new reader only against the **immediately prior schema**.
- Backward transitive requires the new reader to read **every prior schema in the supported set**, e.g., v1, v2, and v3.
- The same distinction applies to forward and full transitive checks.

Never assume "v4 is backward compatible with v3, so v4 can read v1"; compatibility is not automatically transitive across arbitrary edits.

### 2.4. Schema Compatibility Checks Do Not Verify Business Rules

A Schema Registry can confirm an Avro reader schema resolves a writer schema, yet it cannot know:

- Whether `amount` is VND or USD.
- Whether `eventId` stays stable across retries.
- Whether a customer consented to share `phone`.
- Whether enum `CANCELLED` breaks a domain state machine.
- Whether `shipmentCreated` preserves ordering invariants.

Therefore, combine **schema compatibility tests + semantic contract tests**.

## 3. Adding Fields in JSON: Why "Optional" Is Not Always Safe

JSON contract v1:

~~~json
{
  "eventId": "evt-100",
  "orderId": "ORD-100",
  "amountMinor": 150000
}
~~~

Producer v2 adds a field:

~~~json
{
  "eventId": "evt-100",
  "orderId": "ORD-100",
  "amountMinor": 150000,
  "currency": "VND"
}
~~~

This looks purely additive. Yet:

- A **strict** reader v1 may reject `currency` as an unknown field.
- A reader v2 may require non-null `currency` and reject old payloads.
- A reader v2 may default to `USD`, corrupting historical VND orders.
- A consumer enforcing JSON Schema `additionalProperties: false` may reject the new payload.
- An API gateway/WAF or generated client may enforce closed models.
- A cache serializer or DB JSON reader may have a different policy than the HTTP mapper.

### 3.1. Writer/Reader Compatibility Example

| Scenario | Expected outcome | Condition |
| --- | --- | --- |
| Reader v1 reads JSON v1 | OK | Legacy fields valid |
| Reader v1 reads JSON v2 | OK if unknown fields allowed | Ignores `currency` or uses version dispatch |
| Reader v2 reads JSON v1 | OK if missing field supported | Has **business-valid** default or explicit unknown marker |
| Reader v2 reads JSON v2 | OK | Both schema and semantics valid |

"Optional" means **accepting absent**; it does not automatically mean **optional null** or **optional empty string**. Define all three explicitly.

### 3.2. Absent, Null, and Value Are Three States

~~~json
{"orderId":"ORD-100"}
~~~

~~~json
{"orderId":"ORD-100","currency":null}
~~~

~~~json
{"orderId":"ORD-100","currency":"VND"}
~~~

You may need to distinguish:

- **Absent:** old writer did not know about the field; new reader applies legacy policy.
- **Null:** writer knows the field and explicitly sent no value or cleared it (especially in PATCH).
- **Value:** writer supplied a valid value.
- **Empty string:** a blank string value, not equivalent to null.

For `PATCH`, absent normally means "keep unchanged," whereas null means "clear" or "set to null"; publish those API semantics rather than leaving them to Jackson's defaults.

## 4. Jackson DTOs: Tolerating New Fields Without Breaking Old Clients

Example consumer v1 built to skip newly added fields it does not understand:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderConfirmedV1(
        String eventId,
        String orderId,
        long amountMinor) {
}
~~~

JSON v2 carrying `currency` deserializes into `OrderConfirmedV1` because this annotation tells Jackson to ignore unknown properties.

**Use only when the contract permits**: financial commands should stay strict on risky fields or security metadata; ignoring all unknown fields can mask typos like `amoutMinor` instead of `amountMinor`.

### 4.1. DTO v2 Reading JSON v1

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderConfirmedV2(
        String eventId,
        String orderId,
        long amountMinor,
        String currency) {

    public String effectiveCurrency() {
        if (currency != null && !currency.isBlank()) {
            return currency;
        }
        // Valid ONLY if the v1 contract strictly guaranteed VND.
        return "VND";
    }
}
~~~

**Warning:** Hardcoding `"VND"` is valid only if the v1 contract guaranteed every `amountMinor` was VND. If v1 orders spanned multiple currencies, the new reader **cannot guess** the currency from a missing field. Look up authoritative metadata, tenant policy, or mark `UNKNOWN` for reconciliation.

### 4.2. Validate Required Fields Explicitly

With a Java record:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.PositiveOrZero;

public record CreateOrderRequest(
        @NotBlank String externalId,
        @PositiveOrZero long amountMinor,
        @NotBlank String currency) {
}
~~~

Controller:

~~~java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    private final OrderApplicationService orders;

    OrderController(OrderApplicationService orders) {
        this.orders = orders;
    }

    @PostMapping("/v2/orders")
    ResponseEntity<OrderReceipt> create(
            @Valid @RequestBody CreateOrderRequest request) {
        return ResponseEntity.ok(orders.create(request));
    }
}
~~~

To activate Bean Validation, include the matching `spring-boot-starter-validation` dependency. `@Valid` validates the DTO after deserialization; it does not check caller authorization or transaction idempotency.

A common trap: primitive `long amountMinor` binds to `0` when omitted, making absent indistinguishable from zero. When presence matters, use boxed `Long` with `@NotNull`, or explicit JSON property-presence validation; never rely on primitive defaults.

### 4.3. When Strict Mode Makes Sense

In a service, you might configure:

~~~yaml
spring:
  jackson:
    deserialization:
      fail-on-unknown-properties: true
~~~

This is standard in Spring Boot / Jackson 2. In Spring Boot 4 / Jackson 3, property names or module classes may change; verify against your exact version before copying. Strict mode catches typos and out-of-contract fields, yet breaks clients on any additive response field until upgraded.

**You do not have to apply lenient or strict globally across the whole app.** Choose per boundary: keep public command APIs strict; use envelopes/versions and adaptive readers for event consumers; let trusted response readers skip unknown fields while still validating required values and semantics.

### 4.4. Unit Tests Reading Old and New Payloads

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class OrderJsonCompatibilityTest {

    private final ObjectMapper mapper = new ObjectMapper();

    private static final String V1 =
            """
            {"eventId":"evt-100","orderId":"ORD-100",
             "amountMinor":150000}
            """;

    private static final String V2 =
            """
            {"eventId":"evt-100","orderId":"ORD-100",
             "amountMinor":150000,"currency":"VND"}
            """;

    @Test
    void oldReaderAcceptsAddedFieldWhenConfigured() throws Exception {
        OrderConfirmedV1 result =
                mapper.readValue(V2, OrderConfirmedV1.class);

        assertEquals("ORD-100", result.orderId());
    }

    @Test
    void newReaderHandlesLegacyPayloadWhenDefaultIsValid()
            throws Exception {

        OrderConfirmedV2 result =
                mapper.readValue(V1, OrderConfirmedV2.class);

        assertEquals("VND", result.effectiveCurrency());
    }

    @Test
    void newReaderHandlesNewPayload() throws Exception {
        OrderConfirmedV2 result =
                mapper.readValue(V2, OrderConfirmedV2.class);

        assertEquals("VND", result.currency());
    }
}
~~~

This example uses Jackson 2 imports. Testing with a bare `new ObjectMapper()` differs from Spring Boot's configured mapper with custom modules, naming strategies, or enum settings. Add integration tests injecting the **application's real mapper**, especially for `Instant`, decimals, enums, and polymorphism.

### 4.5. Semantic Contract Tests Matter More Than "Deserializes Without Errors"

~~~text
Given v1 payload missing currency
When reader v2 deserializes
Then currency is marked LEGACY_VND per v1 contract
And amountMinor remains in minor units
And no implicit FX conversion occurs
~~~

If the v1 contract never guaranteed currency, the assertion above is **invalid**. Never invent an unverified assumption as a "default" just to make tests pass.

## 5. Removing Fields: Almost Always Requires Multiple Phases

Suppose event v1 is:

~~~json
{
  "eventId":"evt-200",
  "orderId":"ORD-200",
  "customerName":"Nguyen A",
  "customerId":"CUST-10"
}
~~~

You want to remove `customerName` due to PII concerns and keep only `customerId`.

**Dangerous abrupt change:**

~~~json
{
  "eventId":"evt-200",
  "orderId":"ORD-200",
  "customerId":"CUST-10"
}
~~~

An older consumer may display `customerName` or require it in validation. Dropping it immediately in producer v2 can break parsing in old consumers or worse, silently write empty names.

### 5.1. Expand → Migrate → Contract

~~~mermaid
flowchart TD
    A["v1: customerName required"] --> B["EXPAND: add customerId, keep customerName"]
    B --> C["MIGRATE: upgrade readers to use customerId"]
    C --> D["VERIFY: telemetry shows no legacy readers"]
    D --> E["CONTRACT: producer stops emitting customerName"]
    E --> F["CLEANUP: deprecate schema, retention/replay policy"]
~~~

A realistic plan:

1. **Expand writer:** add the new field while retaining the old field if safe and allowed by policy.
2. **Expand reader:** readers accept both fields, preferring the new one when present.
3. **Migrate:** update every consumer—including batch jobs, DLQ replay tools, and partner SDKs.
4. **Measure:** monitor old-field consumption and active legacy deployments.
5. **Contract:** drop the old field only when no reader still depends on it, or introduce a new major version/topic.
6. **Data retention:** preserve the ability to read old payloads lingering in Kafka topics, DB outboxes, DLQs, and caches.
7. **Cleanup:** remove fallback code after the committed support window once evidence confirms zero usage.

### 5.2. Removing a Field Differs from Renaming a Field

Changing `customerName` to `buyerName` is **remove + add** from a schema standpoint, not a harmless rename. A team can rename the Java property while preserving `@JsonProperty("customerName")` on the wire to keep the legacy contract intact.

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public record BuyerView(
        @JsonProperty("customerName")
        String buyerName) {
}
~~~

This DTO renames the Java accessor to `buyerName()` while keeping the **JSON wire key as `customerName`**. To change the wire key itself, use a phased migration or a separate versioned DTO/endpoint.

### 5.3. Aliases During Transition

~~~java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

public record CustomerInput(
        @JsonProperty("customerId")
        @JsonAlias({"legacyCustomerId"})
        String customerId) {
}
~~~

`@JsonAlias` allows **reading** legacy names during deserialization; it does not emit all aliases during serialization. Output here still writes `customerId`. If both the new field and the alias appear with differing values, define and test an explicit conflict policy instead of guessing which one Jackson keeps.

### 5.4. When an Old Field Cannot Be Kept

Fields containing PII or secrets sometimes **must** be removed immediately for legal or security reasons. In those cases, isolate via a new API major version, new topic/queue, redacting transition adapter, explicit breaking-change notice, and migration plan rather than continuing to broadcast sensitive data solely for backward compatibility.

Compatibility is an engineering goal; it **never overrides security or data-minimization requirements**.

## 6. Adding Required Fields and Changing Defaults

A field newly marked **required** by producer v2 can prevent reader v2 from reading v1 payloads unless a valid default exists.

V1 example:

~~~json
{"orderId":"ORD-1","amountMinor":5000}
~~~

Schema v2 requires:

~~~json
{"orderId":"ORD-1","amountMinor":5000,"currency":"VND"}
~~~

If reader v2 rejects missing `currency`, then `R2 × W1` is **incompatible**. Three options exist:

- Initially declare `currency` optional, tightening to required only once all writers are upgraded and no legacy payloads remain.
- Supply a default proven true for **every** v1 payload within the supported window.
- Introduce schema v2 / a new topic / a new endpoint with version dispatch instead of having reader v2 read v1 directly.

### 6.1. Three Kinds of Defaults

| Default category | Example | When it is safe |
| --- | --- | --- |
| Technical | `retryCount=0` | Does not alter business semantics |
| Historical contract | `currency=VND` | V1 **explicitly guaranteed** all amounts were VND |
| Speculative guess | `country=VN` guessed from recent data | **Unsafe** for any differing data |

A default that makes deserialization succeed while introducing a **silent business bug** is worse than a noisy parse failure.

### 6.2. Required, Non-Null, and Non-Empty Are Not the Same

- Required: the key must appear per schema.
- Non-null: the value must not be JSON `null`.
- Non-blank: strings must not be empty or whitespace-only.
- Positive: numbers must be strictly greater than 0.
- Allowed enum/domain: values must satisfy policy and state machines.
- Immutable: may appear, yet cannot change across updates.

Schema validation and Bean Validation must express each constraint accurately. Tightening validation on an existing field can itself be a **breaking change** even if the JSON schema shape stays identical.

## 7. Changing Field Types and Numeric Types

Seemingly minor type changes easily break the wire:

| Change | Risk | Safe evolution |
| --- | --- | --- |
| `int` → `long` | Older readers may overflow | Keep within old range or issue new version |
| `number` → `string` | Deserialization/validation differs | New field or adapter |
| `amount=120.50` → `amountMinor=12050` | Changes units and meaning | New field + documented units |
| ISO timestamp string → epoch millis | Parsers fail | New field name or explicit version |
| `status="PAID"` → `status=3` | Enum representation change | Keep stable wire values |
| `orderId` string → object | Structural break | Add separate `order` object |
| `nullable` → `non-null` | Historical nulls fail | Verified migration/default |
| Numeric/string ID normalization | Leading zeros lost | Treat opaque identifiers as strings |

### 7.1. Money and Precision

Never use `double` for monetary calculations requiring fixed precision. Specify `amountMinor` as minor-unit counts alongside ISO-4217 `currency` and integer bounds. Remember currencies have differing minor units—never assume every currency has 2 decimals.

### 7.2. Timestamps

~~~json
{"occurredAt":"2026-11-21T06:30:00Z"}
~~~

Specify UTC/offset rules, fractional seconds, and clock semantics. Switching to a zoneless local time string is a semantic change that can break ordering and replay.

### 7.3. Java Date/Time

~~~java
import java.time.Instant;

public record EventMetadata(
        String eventId,
        Instant occurredAt) {
}
~~~

With Jackson, register Java Time support (Spring Boot normally configures the mapper when the relevant dependency is present). A unit test using bare `new ObjectMapper()` will not serialize `Instant` the same way Boot's mapper does. Contract tests must use the adapter's real mapper.

## 8. Enums and Business States

Writer v1 emits:

~~~json
{"orderId":"ORD-1","status":"PENDING"}
~~~

Writer v2 adds `PARTIALLY_SHIPPED`:

~~~json
{"orderId":"ORD-1","status":"PARTIALLY_SHIPPED"}
~~~

Reader v1 defines a Java enum:

~~~java
public enum OrderStatus {
    PENDING, CONFIRMED, SHIPPED
}
~~~

When reader v1 binds strings directly to its Java enum, the new value causes an `InvalidFormatException` / deserialization failure. A JSON field typed as "string" in a loose schema can still break a reader's semantics.

### 8.1. Forward-Looking Design

- Where the domain allows, define an explicit `UNKNOWN`/`UNRECOGNIZED` path.
- If a new status cannot be safely handled, **park/DLQ** rather than defaulting to `PENDING`.
- Write exhaustive status-handling tests with metrics/logs per variant.
- Plan rollout order: readers understand the new state **before** writers emit it.
- If state machines change, test transitions and idempotency carefully.

Example:

~~~java
public enum OrderStatus {
    PENDING,
    CONFIRMED,
    SHIPPED,
    PARTIALLY_SHIPPED,
    UNKNOWN
}
~~~

Merely adding `UNKNOWN` to the enum **is not enough** for Jackson to map unrecognized strings automatically; configure deserialization features or a custom mapper per version. And handling `UNKNOWN` must fail safe—never trigger refunds or shipments based on guesswork.

## 9. JSON Schema: Open vs. Closed Objects

JSON Schema is commonly used to enforce field types, required keys, and restrict unexpected fields.

Illustrative v1 schema:

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["eventId", "orderId", "amountMinor"],
  "properties": {
    "eventId": {"type": "string"},
    "orderId": {"type": "string"},
    "amountMinor": {"type": "integer"}
  },
  "additionalProperties": false
}
~~~

With `additionalProperties: false`, a v2 object carrying `currency` is **invalid** under the v1 schema. When forward compatibility is required, you may need open objects, an extension namespace, or version dispatch.

### 9.1. When Is Strict Unknown-Field Rejection Right?

A write API accepting payment commands may reject extra fields so callers never believe unsupported semantics took effect:

~~~json
{"amountMinor":100000,"currency":"VND","refundImmediately":true}
~~~

If the server silently ignored `refundImmediately`, the caller might mistakenly assume the refund executed. For commands with side effects, strict validation or explicit capability negotiation is safer than open schemas.

**No single unknown-property setting fits every API.** Distinguish **read-oriented events/responses** from **commands**; choose based on threat model and operational contract.

## 10. REST APIs: Request and Response Evolve Independently

Suppose `POST /v1/orders` accepts:

~~~json
{
  "externalId":"ORD-100",
  "amountMinor":120000
}
~~~

Response v1:

~~~json
{
  "id":"100",
  "status":"ACCEPTED"
}
~~~

Server v2 wants to support `currency` on the request and `operationId` on the response.

### 10.1. Request Side

- The new server must accept old requests omitting `currency` to remain compatible with old callers.
- New callers sending `currency` will fail if old server pods remain behind the load balancer—so deploy **readers before writers**.
- Before tightening optional to required, wait until every caller upgrades or introduce a v2 endpoint.
- If the old server is strict, even an additive request field breaks during rolling deployment.

### 10.2. Response Side

- A new server emitting `operationId` is safe for old callers only if they ignore unknown response fields.
- Old server pods do not emit `operationId`; new callers must tolerate it being absent during rollback or rolling upgrades.
- Never change response `status="ACCEPTED"` to `"COMPLETED"` merely to match a UI label; that is a semantic contract break.
- If responses are cached in a CDN or Redis, cache keys and TTLs may hold mixed versions.

### 10.3. HTTP Compatibility Rollout

~~~mermaid
sequenceDiagram
    participant OldClient as Caller v1
    participant NewClient as Caller v2
    participant Server as Server rollout
    Note over Server: Phase A: deploy reader accepting v1 + v2
    OldClient->>Server: v1 request
    Server-->>OldClient: v1-compatible response
    Note over Server: Phase B: new clients begin sending v2 fields
    NewClient->>Server: v2 request
    Server-->>NewClient: Compatible response
    Note over Server: Phase C: contract/deprecate v1 after deadline
~~~

When pods run mixed versions concurrently, ensure bidirectional compatibility or accurate canary routing. Feature flags can suppress emitting new fields/enums even after new code is deployed.

## 11. API Versioning: URI, Header, or Media Type?

Not every change warrants bumping to `/v2`. Additive changes with stable semantics can stay on the existing version if consumers tolerate them.

| Strategy | Example | Strengths | Trade-offs |
| --- | --- | --- | --- |
| URI major version | `/api/v2/orders` | Easy to route, document, and test | Multiple endpoint versions coexist |
| Header | `X-API-Version: 2` | Stable URI | Proxies and caches must vary on header |
| Media type | `Accept: application/vnd.example.order.v2+json` | Idiomatic content negotiation | Complex for SDKs and caching |
| Event envelope | `schemaVersion: 2` | Clean dispatch per event version | Payloads still need durable contracts |
| Schema Registry ID | Wire envelope / schema ID | Registry enforces compatibility | Consumers must share serialization setup |
| Separate topic/queue | `orders.confirmed.v2` | Clean isolation for breaking changes | Dual publish/consume and migration effort |

**Distinguish major versions from compatible minor evolutions.** Pick an operationally manageable strategy and document retirement windows. Never use deployment timestamps as schema versions.

### 11.1. Caching and HTTP `Vary`

When responses depend on `Accept` or version headers, caches and reverse proxies must separate variants (e.g., via `Vary`) or include the version in the cache key. Otherwise a v1 client may receive an unsupported v2 payload.

### 11.2. Spring HTTP Interfaces

~~~java
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.bind.annotation.PathVariable;

@HttpExchange("/v1")
public interface OrdersHttpApiV1 {

    @GetExchange("/orders/{id}")
    OrderReceiptV1 getOrder(@PathVariable String id);
}
~~~

~~~java
public record OrderReceiptV1(String id, String status) {
}
~~~

The interface is only a **client contract in code**; it does not version or validate the server schema. When the server introduces v2, create a separate `OrdersHttpApiV2` with dedicated DTOs rather than mutating v1 types and breaking every existing caller.

Proxies are created via `HttpServiceProxyFactory` over `RestClient` or `WebClient` adapters depending on Spring Framework version; transport configuration remains responsible for TLS, auth, and timeouts.

## 12. Event-Driven Contracts: Kafka and RabbitMQ

An event represents a **fact that occurred** or a message with published semantics. When a producer changes payloads, a lagging consumer or one replaying a Kafka topic from the beginning may encounter thousands of records written with old schemas.

### 12.1. Recommended Envelope

~~~json
{
  "eventId": "b63a4b6f-0a10-4bb7-962b-783e54b3302a",
  "eventType": "OrderConfirmed",
  "schemaVersion": 2,
  "aggregateId": "ORD-100",
  "aggregateVersion": 7,
  "occurredAt": "2026-11-21T06:30:00Z",
  "payload": {
    "orderId": "ORD-100",
    "amountMinor": 150000,
    "currency": "VND"
  }
}
~~~

Explanation:

- `eventId`: immutable identity of the logical event, used by inbox/idempotency.
- `eventType`: logical event name, never a trusted Java class name.
- `schemaVersion`: selects the parser/adapter; distinct from aggregate version.
- `aggregateId`: identity of the domain aggregate.
- `aggregateVersion`: supports ordering and stale-event detection.
- `occurredAt`: when the event happened per contract; not receive time.
- `payload`: version-specific domain payload.

**An `eventId` must remain identical when the outbox relay retries.** Generating a fresh `eventId` solely because schema serialization changed can cause consumers to apply side effects twice.

### 12.2. JSON Envelope DTO

~~~java
import java.time.Instant;
import com.fasterxml.jackson.databind.JsonNode;

public record EventEnvelope(
        String eventId,
        String eventType,
        int schemaVersion,
        String aggregateId,
        long aggregateVersion,
        Instant occurredAt,
        JsonNode payload) {
}
~~~

`JsonNode` lets you pick a parser by `eventType`/`schemaVersion`, provided you still validate schemas, size/depth, allowed event types, and authorization. Never read arbitrary Java class names from untrusted headers to deserialize dynamically.

### 12.3. Explicit Version Dispatch

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;

public class OrderEventDecoder {

    private final ObjectMapper mapper;

    public OrderEventDecoder(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public CanonicalOrderConfirmed decode(EventEnvelope envelope)
            throws Exception {

        if (!"OrderConfirmed".equals(envelope.eventType())) {
            throw new IllegalArgumentException(
                    "Unsupported event type");
        }

        return switch (envelope.schemaVersion()) {
            case 1 -> {
                OrderConfirmedV1 old =
                        mapper.treeToValue(
                                envelope.payload(),
                                OrderConfirmedV1.class);

                yield mapLegacy(old);
            }
            case 2 -> {
                OrderConfirmedV2 current =
                        mapper.treeToValue(
                                envelope.payload(),
                                OrderConfirmedV2.class);

                yield mapCurrent(current);
            }
            default -> throw new UnsupportedSchemaVersionException(
                    envelope.schemaVersion());
        };
    }

    // mapLegacy/mapCurrent are domain adapter functions whose
    // conversion semantics must be explicitly defined and tested.
}
~~~

`CanonicalOrderConfirmed` and `UnsupportedSchemaVersionException` are application-specific types; `mapLegacy`/`mapCurrent` are omitted as they depend on your business contract. The benefit is that the parser **never guesses** versions from whichever fields happen to be present or absent.

### 12.4. Upcasting When Replaying Legacy Data

An upcaster converts an older schema event into the **canonical internal model**:

~~~text
Stored Event v1
   -> validate v1 contract
   -> upcast (v1 amountMinor means VND)
   -> CanonicalOrderConfirmed
   -> business handler
~~~

An upcaster must never invent business facts that never existed. If v1 omitted `customerId`, do not fabricate one—look it up from an authoritative source or mark incomplete and park/reconcile.

### 12.5. Schema Versions vs. Events Changing Meaning

If `OrderConfirmed` previously meant "order accepted by API" and later means "payment settled and inventory reserved," the **event meaning** changed. Introduce a new event type like `OrderFulfilled` or `OrderAccepted` rather than incrementing `schemaVersion` under the old name.

## 13. Broker Retention, DLQs, and Consumer Downtime

V1 events can linger in many places:

- Multi-day Kafka topic retention.
- RabbitMQ DLQs or delayed retry queues.
- PostgreSQL outbox/inbox/audit tables.
- S3/object archives used for replay.
- Redis caches whose TTLs have not expired.
- Customer-exported files.
- Log/CDC pipelines.
- Offline mobile or partner clients.

### 13.1. Compatibility Windows Must Outlive Deployments

If an event sits in a DLQ for 90 days, a consumer deployed today that supports only v2 cannot **replay that historical event**. Plan retiring the v1 reader around TTL/retention and manual replay policies, not merely currently running pods.

### 13.2. Kafka Ordering and Versions

Producer v2 may start emitting v2 events while older `v1` events sit ahead in the topic. Upgraded consumers must handle **mixed versions within the same partition**. Schema compatibility does not solve out-of-order business events; use `aggregateVersion` or state transition guards.

### 13.3. RabbitMQ Queues and Schema Drift

RabbitMQ routes messages via exchanges, queues, and bindings without inspecting JSON schemas. With multiple producers sharing a queue, a consumer can receive v1 and v2 simultaneously. For breaking changes, consider new queues, new routing keys, dual consumers, or adapters, and monitor DLQs closely.

## 14. Avro Schema Registry: Reading and Writing Across Two Schemas

Avro separates **writer schema** and **reader schema**, defining exact compatibility rules. When a new reader decodes binary written with an older schema, Avro applies field-matching and default rules.

### 14.1. Avro v1

~~~json
{
  "type": "record",
  "name": "OrderConfirmed",
  "namespace": "com.example.orders",
  "fields": [
    {"name": "eventId", "type": "string"},
    {"name": "orderId", "type": "string"},
    {"name": "amountMinor", "type": "long"}
  ]
}
~~~

### 14.2. Avro v2 Adding `currency` with a Default

~~~json
{
  "type": "record",
  "name": "OrderConfirmed",
  "namespace": "com.example.orders",
  "fields": [
    {"name": "eventId", "type": "string"},
    {"name": "orderId", "type": "string"},
    {"name": "amountMinor", "type": "long"},
    {"name": "currency", "type": "string", "default": "VND"}
  ]
}
~~~

For `reader v2 × writer v1`, `currency` is **absent in writer v1**, so Avro reader schema v2 fills in default `"VND"`. For `reader v1 × writer v2`, the older reader ignores the new writer field. Under **schema resolution**, this can be fully compatible.

**However:** default `"VND"` is valid only if all v1 events genuinely used VND. Schema Registry cannot verify that business fact.

### 14.3. Adding a Nullable Field with a Default

~~~json
{
  "name": "promotionCode",
  "type": ["null", "string"],
  "default": null
}
~~~

Using a union with `null` and default `null` gives new readers explicit behavior when older writers omit the field. In Avro, defaults must match the first branch type of the union under the specification; never assume any nullable union works if branch order and default value disagree.

### 14.4. Removing a Field in Avro

Suppose v1 had `customerName` and v2 removes it:

- Reader v2 skips the field in writer v1 → typically **backward** compatible in resolution.
- Reader v1 reading writer v2: if reader v1 **requires the field** without a default, resolution fails → **forward incompatible**.
- If reader schema v1 had a valid default for the removed field, reading new records may resolve, though semantics still require verification.

Never assume "removing fields in Avro is always safe." Confirm the compatibility mode and both writer/reader directions.

### 14.5. Schema Registry Compatibility Modes

Systems like Confluent Schema Registry commonly support:

| Mode | General check meaning |
| --- | --- |
| `BACKWARD` | New schema reads data written by the immediately prior version |
| `BACKWARD_TRANSITIVE` | New schema reads data written by all prior versions in the subject |
| `FORWARD` | Prior reader reads data written by the new schema |
| `FORWARD_TRANSITIVE` | All prior readers read data written by the new schema |
| `FULL` | Both backward and forward with the immediately prior version |
| `FULL_TRANSITIVE` | Bidirectional across all prior versions |
| `NONE` | No compatibility enforcement |

Confirm exact names and behavior against **your actual Schema Registry**; different registries vary in terminology and rules. Registry compatibility is a **necessary gate, not a sufficient one**; it never replaces semantic tests, privacy checks, or deployment coordination.

### 14.6. Subject Naming and Mixed Event Types

A Kafka topic may carry multiple event types. Compatibility scope varies depending on subject naming strategy (by topic vs. by record). Never assume a registry automatically understands `eventType` inside your envelope. Design topic, subject, record namespaces, and permissions before deploying.

## 15. Protobuf: Preserve Field Numbers and Reserve Retired Tags

Protobuf wire format identifies fields by **field numbers**, not merely field names. Example:

~~~protobuf
syntax = "proto3";

package example.orders;

message OrderConfirmed {
  string event_id = 1;
  string order_id = 2;
  int64 amount_minor = 3;
}
~~~

Adding a new field:

~~~protobuf
syntax = "proto3";

package example.orders;

message OrderConfirmed {
  string event_id = 1;
  string order_id = 2;
  int64 amount_minor = 3;
  string currency = 4;
}
~~~

Many Protobuf runtimes skip or preserve unknown field numbers depending on runtime and operations. Still, test **application behavior**, not only wire parsing.

### 15.1. Removing Fields Must Reserve Numbers and Names

~~~protobuf
syntax = "proto3";

package example.orders;

message OrderConfirmed {
  string event_id = 1;
  string order_id = 2;
  int64 amount_minor = 3;

  reserved 4;
  reserved "currency";
}
~~~

When removing an active field, add `reserved` so future edits never reuse the field number or name. Never repurpose an old field number for a new meaning: legacy binary bytes will be decoded as the wrong field.

### 15.2. Protobuf Presence and Defaults

In proto3, traditional scalar fields default to zero/empty and do not always distinguish absent from explicit default without field presence tracking. Use `optional` or wrapper/message types when distinguishing "omitted" from "explicitly sent default" is required.

Switching `quantity=0` from "unset" to "valid zero quantity" demands a semantic migration plan, because wire compatibility alone is not enough.

### 15.3. Risky Protobuf Changes

- Changing a field number or reusing a deleted number.
- Changing to an incompatible wire type.
- Altering `packed`/`repeated`/cardinality/`oneof` semantics without testing.
- Changing units or meaning while keeping the same tag.
- Adding enum values that break exhaustive application switches.
- Changing message types so un-upgraded consumers lose compatibility.
- Using Protobuf JSON serialization and assuming it shares binary compatibility rules.

**Protobuf binary compatibility and Protobuf JSON compatibility are not identical.** When Protobuf passes through JSON gateways or HTTP, test field names, unknown-field behavior, and parser rules separately.

## 16. SOAP/XML/XSD and Namespace Versioning

XML/SOAP contracts rely on XSD/WSDL. "Adding an optional element" is not automatically compatible with old clients if the schema uses a strict `xs:sequence` rejecting unexpected elements.

### 16.1. XSD v1

~~~xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="urn:example:order:v1"
           xmlns="urn:example:order:v1"
           elementFormDefault="qualified">
  <xs:element name="OrderConfirmed">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="orderId" type="xs:string"/>
        <xs:element name="amountMinor" type="xs:long"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
~~~

### 16.2. Adding Optional `currency` at the End of the Sequence

~~~xml
<xs:element name="currency"
            type="xs:string"
            minOccurs="0"/>
~~~

Place new elements in the exact `xs:sequence` position if old payloads must validate against v2 XSD. Yet **old clients** validating new XML against v1 XSD will reject the unknown element. JAXB-generated classes and versioned WSDL bindings also impose constraints.

### 16.3. Upgrading SOAP Partners Safely

1. Verify which WSDL/XSD files clients actually validate against.
2. Never change namespaces or service QNames unexpectedly.
3. Add optional elements only if old clients accept them or under an explicit contract version.
4. For breaking changes, publish a new v2 WSDL/namespace/endpoint.
5. Test JAXB/XML parsers against both old and new responses.
6. Keep SOAP fault versioning and error mappings consistent.
7. XML Signature / WS-Security does not guarantee schema compatibility.
8. Check XXE/XML parser hardening and payload size limits when adding XML elements.

### 16.4. `xsi:nil` and Missing

In XML, an omitted element, an empty element, and `xsi:nil="true"` can carry three distinct meanings. `minOccurs="0"` and `nillable="true"` are independent concepts. Test both explicitly in Java/JAXB or Spring Web Services mappings.

## 17. Contracts in Databases and Caches

Even when code owns its database, schema migrations act as a **contract between old and new application code**.

### 17.1. Add Nullable Columns First

Suppose the legacy `orders` table is:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    amount_minor BIGINT NOT NULL
);
~~~

You need to add `currency`:

~~~sql
ALTER TABLE orders
    ADD COLUMN currency VARCHAR(3);
~~~

Starting nullable allows old code to keep inserting rows without supplying the new column. Then:

1. Deploy new code that reads `currency` with proper handling for legacy nulls.
2. Backfill legacy rows from an authoritative source.
3. Deploy new writers that always populate `currency`.
4. Verify zero nulls remain in the supported scope.
5. Only when safe, apply `NOT NULL` / constraints.
6. Check rollback: will rolled-back old code resume inserting nulls?

Never add `NOT NULL` prematurely while old pods or batch jobs are still inserting rows; deployments will fail even though new code passed tests.

### 17.2. Renaming Columns via Expand-Contract

To rename `customer_name` to `customer_display_name`:

~~~text
Phase 1: Add new nullable column
Phase 2: New reader understands old and new
Phase 3: Backfill / dual-write or DB sync strategy
Phase 4: All readers switch to new column
Phase 5: Stop old writes, verify
Phase 6: Drop old column in later release
~~~

Dual-writes carry inconsistency risk. If using DB triggers to sync, test recursion, performance, permissions, and rollback. If using application-level dual-writes, keep both writes in one transaction and handle concurrency/versioning.

### 17.3. JSONB/Event Tables Also Have Schema Contracts

PostgreSQL `payload JSONB` does not mean you can mutate shapes arbitrarily. Old and new outbox relays, analytics jobs, and DLQ replayers must understand historical payloads. `schema_version` can live in an envelope or header, yet must be persisted **alongside the durable event intent**.

### 17.4. Redis Cache Serialization

Cache value v1:

~~~json
{"id":"ORD-100","status":"CONFIRMED"}
~~~

Cache value v2:

~~~json
{"id":"ORD-100","status":"CONFIRMED","currency":"VND"}
~~~

If both versions share a key while readers differ, old readers can fail or apply bad defaults. Mitigations:

- Backward-compatible serializers/deserializers.
- Versioned cache key prefixes like `order:v2:ORD-100` for breaking changes.
- Short TTLs plus controlled invalidation where acceptable.
- Dual-read with fallback/migration when needed.
- Never flush an entire Redis cluster on a DTO change without a capacity plan.

Caches store derived data, yet still require rollout discipline—especially to avoid cache stampedes after invalidation.

## 18. Outbox, Inbox, Idempotency, and Schema Evolution

An outbox event carries both identity and schema:

~~~sql
CREATE TABLE integration_outbox (
    event_id UUID PRIMARY KEY,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    schema_version INTEGER NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(24) NOT NULL
);
~~~

The relay may resend an event days later. Do not re-serialize a v1 event into v2 with altered semantics and pretend it is the same fact unless governed by an explicit **transformation/versioning contract**.

### 18.1. `eventId` Stays Stable Across Retries

~~~text
Outbox E-100 schemaVersion=1
    -> first publish broker ACK lost
    -> retry E-100 (same eventId, payload or documented upcast)
    -> consumer inbox dedup E-100
~~~

If a producer upgrade causes retries to generate a new `eventId`, consumers may apply business side effects twice. If a schema conversion legitimately creates a new event identity, treat it explicitly as a **new event** and enforce business-layer idempotency keys.

### 18.2. Inbox Deduplication Ignores Schema Version

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Never accidentally include `schema_version` in the deduplication primary key: doing so causes the same `eventId` replayed under v1 and v2 to be treated as **two separate events**. Schema version is decoding metadata, not business identity.

### 18.3. Where Do Unknown Versions Go?

When a consumer receives an unsupported `schemaVersion=99`:

- Never mis-parse it as v2 or silently drop it.
- Park/DLQ it under error category `unsupported_schema_version`.
- Retain the `eventId`, securely handled raw bytes, metadata, and retention rules.
- Never ACK as "business applied" without a durable handoff or explicit policy.
- Alert the contract owner and inspect producer rollout state.
- Once readers are updated, replay safely with inbox deduplication.

**Poison messages** caused by incompatible schemas are permanent failures for the running consumer version; tight retry loops will not heal them.

## 19. Rollout Order: Deploy Readers Before Writers

### 19.1. Adding a Field

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant C1 as Consumer old
    participant C2 as Consumer new
    Note over P,C1: Phase 0: both understand v1
    Note over C2: Phase 1: deploy reader supporting v1+v2
    P->>C2: Produce v1 payload
    Note over P: Phase 2: enable v2 field once readers are ready
    P->>C2: Produce v2 payload
    Note over C1: Phase 3: retire/upgrade consumer old
~~~

With uncoordinated deployments, two patterns apply:

- **Reader-first:** producers keep emitting v1 until every reader accepts v2.
- **Compatibility-first:** producer v2 can emit additive fields early only once every v1 reader is proven to handle unknown fields safely.

Never assume every client or partner can upgrade immediately. Even one offline mobile app or un-upgraded partner batch job can break.

### 19.2. Removing a Field

~~~text
T0: Producer P1 emits {A,B}, Consumer C1 requires B.
T1: C2 deployed; accepts {A,B} and {A}.
T2: Migrate all consumers, including DLQ tools and archives.
T3: P2 emits {A} only.
T4: Retire B after agreed compatibility window.
~~~

If `C1` is still running when `P2` drops `B`, `C1 × P2` fails. That is why field removal spans multiple releases rather than a single commit.

### 19.3. Canaries and Feature Flags

You can deploy the v2 binary with `emitNewField=false` behind a feature flag. Once metrics confirm readers and error rates are healthy, turn it on for a slice of traffic, topic, or tenant before expanding. Ensure caches, message replays, rollbacks, and routing never expose mixed incompatible payloads to unsupported consumers.

### 19.4. Rollback Is Not Simple

Once a new producer writes v2 events into Kafka or PostgreSQL JSONB, rolling consumers back to v1 code can leave them **unable to parse v2 historical payloads**. Code binaries roll back fast; **data rollbacks** often cannot happen at all.

Keep old and new readers compatible throughout the rollback window, or hold feature flags off on new schema emission until rollback is no longer likely.

## 20. Contract Registry and Change Governance

Multi-team integrations need a single source of truth:

- OpenAPI for HTTP endpoints.
- AsyncAPI for event/message APIs, where adopted.
- JSON Schema / Avro / Protobuf schema definitions.
- WSDL / XSD for SOAP/XML.
- Database migrations for SQL.
- ADRs / contract changelogs for business semantics.
- Consumer inventories and compatibility support windows.
- Deprecation/sunset notices and migration guides.

### 20.1. Versioning Does Not Replace Change Management

Every breaking change needs:

1. Reason for the change.
2. Inventory of existing readers and writers.
3. Compatibility matrix.
4. Minimal safe rollout sequence.
5. Migration/backfill plan.
6. Retention, DLQ, and replay impact.
7. Feature flags and rollback conditions.
8. Security and privacy assessment.
9. Test fixtures and contract tests.
10. Owner and deprecation deadline.

### 20.2. Semantic Versioning: Helpful, Not a Substitute for Tests

An API SDK version `2.3.0` or schema revision 12 is metadata; whether a field change breaks depends on actual readers. SemVer communicates contract intent; **bumping only a minor version never turns a breaking change into a compatible one**.

## 21. Four-Combination Contract Testing

For every v1-to-v2 transition, build the matrix:

| Test | Payload | Reader | Required when supported |
| --- | --- | --- | --- |
| Baseline | Writer v1 | Reader v1 | Current baseline |
| Backward | Writer v1 | Reader v2 | Reader-first rollout / replay |
| Forward | Writer v2 | Reader v1 | Mixed deployments / legacy clients |
| New | Writer v2 | Reader v2 | Target state |

Beyond parsing, assert **business semantics**, validation outcomes, defaults, monetary units, tenant permissions, and side effects. Never stop at asserting `ObjectMapper` did not throw.

### 21.1. Golden Fixtures

Store representative serialized payloads in your contract test suite:

~~~text
fixtures/
  order-confirmed-v1.json
  order-confirmed-v2.json
  order-confirmed-v2-missing-currency.json
  order-confirmed-v2-null-currency.json
  order-confirmed-v2-unknown-enum.json
  order-confirmed-v2-extra-field.json
~~~

This tree is an **illustrative test structure**, not a request to create files outside this lesson. Fixtures should cover present/absent fields, nulls, unknowns, min/max boundaries, Unicode, decimals, and malformed inputs.

### 21.2. Separating Schema Compatibility Tests from Semantic Validation

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class NewConsumerContractTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void acceptsOldPayloadWithCorrectHistoricalUnit()
            throws Exception {

        String legacy = """
                {"eventId":"E-10",
                 "orderId":"ORD-10",
                 "amountMinor":10000}
                """;

        OrderConfirmedV2 decoded =
                mapper.readValue(legacy, OrderConfirmedV2.class);

        assertEquals("VND", decoded.effectiveCurrency());
        assertEquals(10000L, decoded.amountMinor());
    }

    @Test
    void doesNotMistakeNullForValidCurrency()
            throws Exception {

        String newPayload = """
                {"eventId":"E-11",
                 "orderId":"ORD-11",
                 "amountMinor":10000,
                 "currency":null}
                """;

        OrderConfirmedV2 decoded =
                mapper.readValue(newPayload, OrderConfirmedV2.class);

        // Example v2 policy rejecting explicit null.
        assertThrows(IllegalArgumentException.class,
                () -> validateV2RequiredCurrency(decoded));
    }

    private void validateV2RequiredCurrency(OrderConfirmedV2 dto) {
        if (dto.currency() == null || dto.currency().isBlank()) {
            throw new IllegalArgumentException(
                    "currency required for v2 payload");
        }
    }
}
~~~

This snippet intentionally separates **legacy missing** from **v2 explicit null** in validation/dispatch. Binding both into one DTO without `schemaVersion` or JSON presence tracking can **erase the difference** between missing and explicit `null`; production code needs version envelopes or `JsonNode.has(...)`/`isNull()` checks prior to mapping.

### 21.3. Consumer-Driven Contract Testing

For REST, tools like Pact or Spring Cloud Contract verify **which fields and endpoints consumers actually rely on**. Providers run consumer-supplied verification contracts in CI before deploying.

Yet consumer-driven tests may miss unregistered consumers, offline mobile clients, or archive replays. Maintain a consumer inventory and retention windows—never treat "green CI contract tests" as proof every external reader has upgraded.

### 21.4. Contract Diff Automation

In CI, diff OpenAPI, JSON Schema, Avro, and Protobuf specs and classify changes:

- Optional field added.
- Required field added.
- Field removed.
- Field renamed.
- Type changed.
- Enum value added.
- Requiredness tightened.
- Default/format/unit changed.
- Endpoint status codes or error responses changed.
- Message routing or version headers changed.

Gating must know the **contract's compatibility policy**: removing a field may pass backward Avro resolution while breaking forward consumers; changing a unit in a field description is breaking even if schema diff tools miss it.

## 22. HTTP and Broker Integration Testing in Spring Boot

### 22.1. REST Adapter Test with `MockRestServiceServer`

Suppose a client uses `RestClient` and an `OrderReceiptV1` DTO that ignores unknown fields:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

class OrdersClientCompatibilityTest {

    @Test
    void oldClientCanReadResponseWithNewField() {
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer mock =
                MockRestServiceServer.bindTo(builder).build();

        RestClient client = builder
                .baseUrl("https://orders.test")
                .build();

        mock.expect(requestTo("https://orders.test/v1/orders/10"))
                .andRespond(withSuccess(
                        """
                        {"id":"10","status":"ACCEPTED",
                         "operationId":"op-100"}
                        """,
                        MediaType.APPLICATION_JSON));

        OrderReceiptV1 result = client.get()
                .uri("/v1/orders/10")
                .retrieve()
                .body(OrderReceiptV1.class);

        assertNotNull(result);
        assertEquals("10", result.id());
        mock.verify();
    }
}
~~~

This is a **compatibility skeleton**: to ensure old clients ignore `operationId`, configure the Jackson converter's unknown-field policy in `RestClient` or annotate `OrderReceiptV1`:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderReceiptV1(String id, String status) {
}
~~~

This unit test verifies JSON response mapping only, not TLS, HTTP connection pools, or timeouts. Integration tests must exercise production-identical client configurations.

### 22.2. Kafka/RabbitMQ with Testcontainers

Verify these criteria:

1. Producer v1 sends an event to consumer v2 and resulting DB business state is correct.
2. Producer v2 sends an event to consumer v1 when forward compatibility is promised.
3. Consumer restarts and processes legacy v1 records still sitting in the topic or DLQ.
4. Unknown schema versions are durably parked rather than ACKed as applied.
5. Untrusted JSON `TypeId`/headers cannot instantiate arbitrary classes.
6. Schema ID/registry outages trigger proper retry/backoff.
7. Producer redelivery with the same `eventId` never duplicates side effects.
8. Out-of-order v1/v2 events are blocked by `aggregateVersion` guards.
9. Queue/topic bindings and routing stay intact or migrate per plan.
10. Broker message-size limits hold when large fields are added.

**Never call `@KafkaListener`/`@RabbitListener` Java methods directly in unit tests** and assume serialization, headers, schema registry, and ACKs work. Test against real broker containers when delivery contracts matter.

### 22.3. SQL Migration Integration Tests

With PostgreSQL Testcontainers:

~~~text
Given schema v1 + legacy rows
When additive migration v2 is applied
Then old application queries/inserts still work during the overlap window
And new application reads old rows cleanly
When backfill completes
Then currency has no unknown values in supported scope
And new writers populate currency
Then only after reader migration apply NOT NULL and drop legacy column
~~~

Run production Flyway/Liquibase scripts directly; H2 does not prove PostgreSQL constraint behavior, locking, JSONB semantics, or online migration performance.

## 23. Compatibility When Changing Error and HTTP Status Fields

API contracts include error payloads too:

~~~json
{
  "code": "ORDER_CONFLICT",
  "message": "Order already exists"
}
~~~

Version v2 adds:

~~~json
{
  "code": "ORDER_CONFLICT",
  "message": "Order already exists",
  "operationId": "op-123",
  "retryable": false
}
~~~

If legacy SDKs only read `code` and ignore extra fields, additive error fields can be safe. Changing `ORDER_CONFLICT` to `DUPLICATE_ORDER` without keeping aliases breaks client mappings even though the JSON types stay strings.

### 23.1. `retryable` Is Not Just a Field

Adding `retryable=true` when the server **may have committed side effects** still requires client idempotency keys. Adding a schema field never makes blind retries safe after unknown timeouts.

### 23.2. HTTP Status Codes Are Part of the Contract Too

Changing `201 Created` to `202 Accepted` changes when the caller considers work complete. Changing `409` to `400` can alter SDK and monitoring classification. Contract tests must assert headers, HTTP statuses, error codes, and idempotency semantics—not just JSON shapes.

## 24. Security and Privacy in Schema Evolution

Adding a new field can widen data exposure:

~~~json
{
  "orderId":"ORD-100",
  "customerEmail":"person@example.org"
}
~~~

Before adding sensitive data to events:

- Verify legitimate need and authorization for every consumer.
- Review topic/queue ACLs, DLQ retention, logs, metrics, and traces.
- Never add secrets, raw access tokens, or passwords.
- When PII is unnecessary, emit opaque identifiers/references instead.
- When retiring a PII field, account for archives, DLQs, and backup retention.
- Check `ObjectMapper` logging and record `toString()` methods for accidental leaks.
- Consider encryption or field-level protection when contracts require it.

Technical compatibility is never a valid excuse to retain sensitive data beyond policy limits.

### 24.1. Schema Aliases and Type Mappings Have an Attack Surface

Never deserialize arbitrary class names from untrusted Kafka/RabbitMQ headers or native Java serialization. Use explicit allowlisted event types and DTO mappings; bound JSON nesting and size, validate business fields, and reject/park untrusted payloads.

## 25. Observability During Contract Transitions

Do not count only HTTP 500s or deserialization exceptions. Track **which versions consumers are reading** and **whether deprecated fields are still used**.

| Metric | Meaning |
| --- | --- |
| `integration.contract.received` by `schema_version` | Actual payload versions in flight |
| `integration.contract.decoded_success` | Parse and validation passes |
| `integration.contract.decode_failure` | Type/field/enum/schema failures |
| `integration.contract.unknown_version` | Events newer than the reader supports |
| `integration.contract.legacy_fallback` | Reader relied on legacy defaults/aliases |
| `integration.contract.field_deprecated_used` | Deprecated field still actively consumed |
| `integration.contract.payload_mismatch` | Same `operationId`, differing payload |
| `integration.contract.dlq_age` | Events stuck waiting on schema fixes |
| `integration.contract.partner_version` | Active partner version where observable |
| `integration.business_applied` | Business side effects actually committed |
| `integration.consumer_duplicate` | Replay deduplicated by `eventId` |

Metric names are **illustrative application instruments**, not assertions that Actuator generates them automatically.

### 25.1. Cardinality

Metric labels should stay bounded—such as `event_type`, `schema_version`, `outcome`, and `downstream`. Never put raw `eventId`, `orderId`, emails, payloads, tokens, or URLs containing secrets into metric tags.

### 25.2. Deprecation Readiness

Before removing a field:

1. Measure how many consumer instances still read the old field (where observable).
2. Account for external clients lacking telemetry.
3. Scan DLQs, backlogs, and archived event types across the compatibility window.
4. Verify rollback contract tests.
5. Send migration notices and confirm partner acknowledgements.
6. Keep a kill switch to stop emitting the new schema on error.
7. Assign an owner for unknown-schema DLQs.

If you cannot verify that old readers are gone, do not delete fields on an unversioned endpoint promising backward compatibility.

## 26. Runbook When Adding/Removing Fields Breaks Integration

| Symptom | Likely cause | Mitigation |
| --- | --- | --- |
| Jackson `UnrecognizedPropertyException` | Strict old reader saw new field | Disable field emission, upgrade reader, or adjust compatibility policy |
| Jackson missing creator property | New required field absent in legacy payload | Supply valid default or version dispatcher |
| `NullPointerException` after deploy | Missing/null left unvalidated | Validate absent/null explicitly and run migration |
| Monetary values wrong without parse error | Bad default or changed unit meaning | Fix semantic contract and reconcile affected records |
| Enum parse failure | Writer emitted new enum value | Reader-first rollout, `UNKNOWN`/park policy |
| Kafka DLQ spike after producer rollout | Consumers lack `schemaVersion` support | Roll back emission, upcast, or upgrade consumers |
| Rabbit listener rejects `TypeId` | Incompatible converter/class mapper | Use allowlisted type mapping and version dispatch |
| REST 400 when sending new field | Strict v1 server pods still active | Reader-first deployment or feature flag |
| Generated client fails after OpenAPI update | Closed/strict client model | Compatibility policy or new major API version |
| SOAP validation failed | XSD sequence/namespace mismatch | WSDL/XSD versioning |
| Redis cache deserialization error | Key holds object written by newer/older schema | Versioned keys, adapters, or controlled invalidation |
| DB insert fails `NOT NULL` | Old writer omits new column | Roll back constraint and finish migration |
| SQL column not found | Code deployed before schema migration | Run expand migration before deploying code |
| Consumer replay fails on month-old events | Non-transitive compatibility | Add upcaster or extend support window |
| Same `eventId` applied twice after upcast | Dedupe key included `schemaVersion` | Deduplicate strictly on logical identity |
| New response leaks unexpected PII | Unreviewed field exposure | Disable field emission, run incident/redaction response |
| Rolled-back code cannot read new data | Data already emitted under new schema | Forward-reader fallback or version routing |

### 26.1. Investigation Order

1. Inspect the actual wire payload and `schemaVersion`, not Java DTO class names.
2. Identify the exact running writer and reader versions.
3. Determine whether failure occurred at deserialization, validation, or business semantics.
4. Pinpoint which field, enum, requiredness, or default edit triggered the failure.
5. Assess impact across broker backlogs, DLQs, outboxes, and databases.
6. If needed, toggle the feature flag off for new field/version emission without deleting message evidence.
7. Deploy a reader adapter/compatibility fix covered by regression fixtures.
8. Replay safely while preserving `eventId` and idempotency.
9. Verify final business state post-replay.
10. Update compatibility policies, changelogs, and CI checks.

## 27. Case Study: `OrderConfirmed` from v1 to v2

### 27.1. Context

- Order Service (producer) publishes Kafka `OrderConfirmed`.
- Inventory (consumer) reads `orderId` and `amountMinor`.
- Billing (consumer) reads `customerName` for invoices.
- Analytics reader processes historical events.
- Redis stores `OrderSummary`.
- A DLQ holds v1 events awaiting replay.
- V2 wants to add `currency` and drop `customerName` for PII minimization.

### 27.2. The Wrong Plan

~~~text
Release 2:
  Producer deletes customerName, adds required currency.
  Deploy producer first.
  Inventory and Billing consumers have not updated yet.
~~~

Consequences:

- Billing loses `customerName` and fails.
- Inventory's strict mapper rejects `currency`.
- New Analytics requiring `currency` fails to parse historical v1 events.
- Replaying v1 DLQ events into new consumers breaks.
- Rolling back the producer cannot erase v2 events already written to the topic.

### 27.3. The Multi-Phase Plan

**Phase A — Prepare Compatibility**

- Audit consumers, event retention, DLQs, and partner data usage.
- Verify whether v1 `amountMinor` was always VND.
- Create v2 schema with `currency` (initially optional or backed by a proven historical default).
- Add a v1 → canonical upcaster if needed.
- Update Billing to look up names by `customerId` instead of `customerName`.
- Add CI schema diffs and golden fixtures.

**Phase B — Reader-First**

- Deploy Inventory, Billing, and Analytics readers supporting both v1 and v2.
- Remove Billing's mandatory dependency on `customerName`.
- Monitor `legacy_fallback`, `unknown_version`, and DLQ metrics.
- If v1 producers lacked `customerId`, run an earlier expand phase adding it first.

**Phase C — Producer Rollout**

- Have producer emit `currency` while retaining `customerName` during the overlap window if policy allows.
- Enable via canary/feature flag and watch error metrics.
- Verify mixed producer/consumer compatibility matrix.

**Phase D — Contract/Deprecation**

- Once no reader requires `customerName` and compliance permits, stop emitting the legacy field.
- If unsafe on the same topic, cut over to a new major event version/topic or redacting adapter.
- Keep readers able to decode historical v1 across retention and replay windows.
- Before tightening `currency` to required, verify historical data/backfills/defaults are complete.

### 27.4. Acceptance Criteria

~~~text
Given a v1 OrderConfirmed event missing currency
When v2 Inventory reader processes it
Then the event is interpreted with the accurate historical currency
And no duplicate reservation is created.

Given a v2 OrderConfirmed containing the new currency
When an old reader within the forward-support window reads it
Then the reader does not crash, or the event routes to a compatible adapter.

Given v2 omits customerName
When Billing reader processes it
Then Billing resolves customerId from the authoritative source
And no legacy PII leaks into new logs or DLQs.

Given a v1 event in the DLQ replayed 60 days later
When the current reader receives the event
Then the version dispatcher decodes v1 cleanly
And preserves eventId for inbox deduplication.
~~~

## 28. Common Anti-Patterns

| Anti-pattern | Why it fails | Replacement |
| --- | --- | --- |
| "Adding a field is always backward compatible" | Strict readers, requiredness, or defaults can break | Full reader/writer matrix |
| Testing only new reader with new writer | Misses rolling-deploy overlap | Test all 4 combinations |
| Changing JSON wire key when renaming a Java property | Wire breaking change | `@JsonProperty` / aliases / migration |
| Dropping a field immediately in the producer | Old readers may still need it | Expand-migrate-contract |
| Guessing default currency by intuition | Silent monetary corruption | Business-valid historical default |
| Using primitives when missing detection matters | Absent becomes zero/false | Boxed types / presence validation |
| Mapping unknown enums to a valid status | Corrupts state machines | `UNKNOWN` / park / fail-safe |
| Changing units while keeping the field name | Semantic breaking change | New field or explicit version |
| Parsing every `schemaVersion` with current DTO | Historical payloads misread | Version dispatcher / upcaster |
| Treating green Schema Registry checks as sufficient | Checks structural resolution only | Semantic contract tests |
| Changing Protobuf field numbers | Wire bytes decoded as wrong fields | Preserve numbers and `reserved` deleted tags |
| Changing XSD sequences without testing old clients | Old XML readers reject payloads | WSDL/XSD compatibility governance |
| Setting strict JSON globally for all consumers | Additive events fail unnecessarily | Per-boundary policy |
| Setting lenient JSON globally for all commands | Typos silently ignored | Strict command validation |
| Switching API 201 to 202 unannounced | Business completion semantics shift | Versioned contract notice |
| Dropping a DB column before deploying code | Old code still queries it | Expand-contract migration |
| Sharing Redis cache keys across breaking v1/v2 schemas | Deserialization failures | Key versioning or adapters |
| Putting `eventId + schemaVersion` in the dedupe key | Replayed events apply twice | Deduplicate on stable logical `eventId` |
| Deleting old readers immediately after rollout | DLQs/archives still hold legacy events | Retention-aware support window |
| Rolling back code without checking new data | Old binary cannot parse new records | Forward-compatible rollback plan |
| Adding PII to schemas "for consumer convenience" | Privacy, ACL, and retention risks | Opaque references / data minimization |

## 29. Pre-Release Checklist for Contract Changes

- [ ] Contract owner and inventory of all readers/writers identified.
- [ ] Request writer/reader and response writer/reader evaluated separately.
- [ ] Compatibility matrix covers `R1/W1`, `R2/W1`, `R1/W2`, `R2/W2`.
- [ ] Backward/forward/full policy and transitive support window documented.
- [ ] Missing, null, empty, and default semantics distinguished and validated.
- [ ] No meaning, unit, or requiredness changes shipped without semantic checks.
- [ ] New field defaults are **proven accurate** for historical data or backed by migration.
- [ ] Removed fields have deprecation, migration, retention, and rollback plans.
- [ ] New unversioned enum values are never emitted before old readers handle them.
- [ ] DTOs, Jackson configs, and Bean Validation match per-boundary policies.
- [ ] OpenAPI/AsyncAPI/JSON Schema/Avro/Protobuf/WSDL/XSD versioned and tested.
- [ ] Avro writer/reader resolution and Schema Registry policies verified.
- [ ] Protobuf field tags kept stable and deleted tags marked `reserved`.
- [ ] SOAP XML namespaces, sequences, `minOccurs`, and `nillable` tested with old clients.
- [ ] DB migrations follow expand-migrate-contract and survive rolling deployments.
- [ ] Redis cache schemas, keys, and TTLs do not break old callers.
- [ ] Event envelopes keep `schemaVersion`, `eventId`, and `aggregateVersion` distinct.
- [ ] Outbox/inbox preserve `eventId` across retries/replays without putting version in dedupe identity.
- [ ] Consumers decode historical events in Kafka/DLQs/archives within promised retention.
- [ ] Unknown versions park/DLQ cleanly without applying business effects.
- [ ] Contract tests run against golden fixtures, real brokers, and SQL migrations as needed.
- [ ] CI runs schema diffs, semantic tests, and canary/feature-flag gates.
- [ ] Rollout order, rollback steps, and partner support deadlines published.
- [ ] Metrics track version distribution, deprecated-field usage, decode failures, and applied effects.
- [ ] Security/privacy review completed whenever PII, secrets, or auth fields are added/removed.

**Remember:** Data contracts outlive individual deployments. "Adding a field" can break strict old readers or trigger bad defaults in new readers; "removing a field" can break lagging clients, broker consumers, and replayable archives. Safe evolution means **defining compatibility per concrete reader/writer pair, separating structural from semantic contracts, deploying readers before writers, applying expand–migrate–contract, dispatching versions explicitly, and testing the entire old–new matrix**. In Spring Boot Integration, pair that with **outbox/inbox, idempotency, SQL migrations, cache discipline, and observability** so data drift never turns into silent business corruption.

## References

- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestClient`, HTTP Interfaces, and contract mapping.
- [Spring Boot — JSON](https://docs.spring.io/spring-boot/reference/features/json.html): auto-configuration and versioned JSON mapping.
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): Bean Validation and boundary validation.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html): request/response schemas and API documentation.
- [JSON Schema Specification](https://json-schema.org/specification): required, nullable alternatives, `additionalProperties`.
- [Apache Avro Specification](https://avro.apache.org/docs/current/specification/): writer/reader resolution, defaults, aliases.
- [Confluent Schema Registry — Schema Evolution](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html): backward/forward/full/transitive modes.
- [Protocol Buffers — Updating a Message Type](https://protobuf.dev/programming-guides/proto3/#updating): safe field numbering, `reserved`, presence.
- [Protocol Buffers — Field Presence](https://protobuf.dev/programming-guides/field_presence/): absent, default, and `optional`.
- [W3C XML Schema Definition](https://www.w3.org/TR/xmlschema11-1/): XML/XSD particles, `minOccurs`, `nillable`.
- [Spring for Apache Kafka — Reference](https://docs.spring.io/spring-kafka/reference/): producers/consumers and message converters.
- [Spring AMQP — Reference](https://docs.spring.io/spring-amqp/reference/): RabbitMQ converters, listeners, and retries.
- [Spring Data Redis — Reference](https://docs.spring.io/spring-data/redis/reference/): caching and Redis serialization.
- [Flyway — Documentation](https://documentation.red-gate.com/fd): versioned DB schema migrations.
- [Spring Cloud Contract](https://docs.spring.io/spring-cloud-contract/reference/): consumer/provider contract verification.
- [Pact — Consumer Driven Contract Testing](https://docs.pact.io/): provider compatibility checks.
- [Enterprise Integration Patterns — Versioning](https://www.enterpriseintegrationpatterns.com/ramblings/09_versioning.html): versioned message contracts.
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): durable event intent and retries.

# Multi-Version Deployments with Compatible Schemas and Contracts

## 1. The Operational Challenge of Upgrading Integrations

In a **Spring Boot Integration** system, a single release rarely upgrades every component at once. Kubernetes may run versions N and N+1 of a service side by side; partner HTTP clients still call old APIs; Kafka consumers process events from months ago; two app versions share one database; outboxes and dead-letter queues still hold messages in older schemas.

An apparently simple change like renaming `customerId` to `buyerId` or changing `amount` from integer to string can break part of the integration pipeline mid-rollout. Worse, code may run without throwing yet misinterpret the **business meaning** of the data.

This lesson teaches how to design **schema/contract evolution compatibility** and safe **concurrent multi-version deployments** across HTTP, databases, caches, message brokers, and Spring Integration adapters. Key topics include:

- Identifying which version **reads** and which version **writes** data at each boundary.
- Distinguishing structural compatibility (*schema*) from semantic compatibility (*contract*).
- Applying **expand → migrate → contract** on shared databases.
- Sequencing producer/consumer upgrades across Kafka, RabbitMQ, and existing outbox/DLT records.
- Performing partial rollouts via rolling updates, canary, or blue-green with genuinely viable rollbacks.
- Testing version matrices and observing compatibility errors in production.

### Running Scenario

Suppose an ordering system consists of:

~~~mermaid
flowchart LR
    W[Web / Mobile / partners] -->|HTTP JSON| A[Order API: N and N+1]
    A --> D[(orders DB)]
    A --> O[(outbox)]
    O --> K[(Kafka orders.events)]
    K --> P[Payment consumer: N and N+1]
    K --> S[Shipping consumer: N]
    P --> H[HTTP Payment Gateway]
    S --> R[(Shipping DB)]
    K --> L[(DLT / retry topics)]
    L --> X[Replay job after bug fix]
~~~

The new version adds `currency` to `OrderPlaced` events and splits shipping address columns in the database. During transition, new producers can emit to old consumers, and new consumers must still process old messages or replays from the DLT.

**Success criteria:** zero lost messages, zero misread currencies or statuses, zero duplicate transactions, and ability to roll back code within the rollback window without restoring the database from backup.

## 2. Compatibility Is Defined by Readers and Writers

"Two versions are compatible" is meaningless as a generic property of a schema file. Specify explicitly **who is the writer** (producer, HTTP server returning responses, code writing to DB) and **who is the reader** (consumer, HTTP client, code querying DB).

| Compatibility Type | Question to Answer | Example |
| --- | --- | --- |
| **Backward compatibility** | Can a **new reader** read **data from an old writer**? | Consumer N+1 processes `OrderPlaced` emitted by producer N |
| **Forward compatibility** | Can an **old reader** read **data from a new writer**? | Consumer N does not fail when producer N+1 adds an optional field |
| **Full compatibility** | Do both directions work? | During rolling updates, readers N and N+1 handle both writers |
| **Transitive compatibility** | Do readers/writers work across all supported historical versions, not just adjacent ones? | Replaying N-3 events when only consumer N+1 remains |
| **Semantic compatibility** | Do business outcomes preserve exact meaning even if parsing succeeds? | Adding `currency` must not make old consumers treat USD as VND |
| **Operational compatibility** | Can versions coexist against DB, broker, config, TLS, quotas, and timeouts during rollout? | Pod N does not crash because N+1's migration dropped a column it needs |

A **reader × writer** matrix to review any concurrent rollout:

| Reader ↓ / Writer → | Writer N | Writer N+1 |
| --- | --- | --- |
| **Reader N** | Baseline must work | **Forward compatibility** required when writer N+1 runs before reader N is gone |
| **Reader N+1** | **Backward compatibility** required while producer N and old data still exist | New path must work |

If outboxes or DLTs still hold N-3 events for replay, expand the matrix to include historical writer columns. Testing only N and N+1 is insufficient.

### Identical Structure Does Not Guarantee Business Compatibility

Suppose message N contains:

~~~json
{
  "eventType": "OrderPlaced",
  "eventId": "evt-10",
  "orderId": "ord-42",
  "amountMinor": 150000
}
~~~

In N+1, a field is added:

~~~json
{
  "eventType": "OrderPlaced",
  "eventId": "evt-11",
  "orderId": "ord-43",
  "amountMinor": 2500,
  "currency": "USD"
}
~~~

Structurally, many old consumers ignore `currency` in JSON. Yet consumer N assumes `amountMinor` is always VND and calculates 2,500 USD as 2,500 VND. That is a **contract-breaking semantic change**, even though decoding raises zero errors.

A safer plan has **two steps**: first upgrade all consumers to understand `currency` while still handling legacy VND; only afterward toggle a feature flag allowing producers to emit multi-currency events. While old consumers remain live, producers must emit only semantics old consumers interpret accurately.

## 3. HTTP/JSON Contract Evolution Rules

### 3.1. Additive vs. Breaking Changes

| Change | Risk Level | Compatibility Condition |
| --- | --- | --- |
| Add **optional** field to JSON response | Usually low | Old clients tolerate unknown fields; new data does not break old rules |
| Add required field in **request** | High | Old clients omit it; new server needs defaults or legacy handling |
| Add new enum value | High even when schema allows strings | Old clients may use exhaustive switches and throw or hit wrong defaults |
| Rename/remove field | High | Old readers rely on it or use unannounced aliases |
| Change type `number → string`, `int → object` | High | Deserializers, validations, and arithmetic fail |
| Change meaning while keeping field name | Very high | Can silently miscalculate data |
| Add optional response header | Usually low | Clients do not hard-assert fixed header sets |
| Change HTTP status / error code | Medium–high | Clients may retry, ignore, or display wrong messages |
| Change auth scope, TLS CA/certificate | Operationally breaking | Requires overlapping trust window and client updates first |

**Additive changes are safe only when the contract specifies optional/default rules and real consumers tolerate them.** Never apply a blanket "ignore all unknown fields" rule to high-security requests: servers may need to reject unpermitted fields to prevent mass assignment or caller intent confusion.

### 3.2. Server Accepting Both Old and New Requests During Transition

Suppose `POST /v1/orders` originally accepted `shippingAddress` as a string. N+1 adds `shippingCity` and `shippingPostalCode`, while client N still sends the old format.

~~~json
{
  "requestId": "req-501",
  "sku": "SKU-18",
  "quantity": 2,
  "shippingAddress": "1 Main St, HCMC"
}
~~~

During transition, the new server may simultaneously receive:

~~~json
{
  "requestId": "req-502",
  "sku": "SKU-18",
  "quantity": 2,
  "shippingAddress": "1 Main St, HCMC",
  "shippingCity": "Ho Chi Minh City",
  "shippingPostalCode": "700000"
}
~~~

The legacy address field stays present for client/consumer N. Define what happens when all three fields arrive: which is the *source of truth* and what happens if they conflict—never pick randomly whichever field appears.

Example Java DTO for **compatibility-period input**:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderRequest(
        @NotBlank String requestId,
        @NotBlank String sku,
        @Min(1) int quantity,
        String shippingAddress,
        String shippingCity,
        String shippingPostalCode) {
}
~~~

In MVC applications, use `@Valid @RequestBody OrderRequest` to trigger Bean Validation with the right validation starter. `@JsonIgnoreProperties(ignoreUnknown = true)` merely illustrates extensibility; for sensitive APIs or write-mapped DTOs, consider **allowlist** validation rejecting uncontracted fields. Wire-format optionality does not let business logic omit the address: validators must ensure **at least one complete address format**, reject conflicting formats, and return stable error codes.

### 3.3. Preserving Error and Retry Contracts

In HTTP integrations, contracts include more than request bodies:

- **URI/path** (e.g., `/v1/orders`), HTTP method, query parameters, and encoding;
- **status codes**, headers (especially `Retry-After` and `Idempotency-Key`);
- **error responses** with stable `code`s distinguishing validation, conflict, rate limit, and unavailable;
- **timeout and retry semantics** for POST/PUT/PATCH;
- **security**: token audience/scopes, mTLS identity, certificate trust, and rotation policies.

For example, if API N returns `409 ORDER_ALREADY_EXISTS` on duplicate `requestId`, changing N+1 to return `200` with the old record can trick client N into thinking a fresh creation succeeded. Document idempotency semantics explicitly and test against client N before changing. For truly breaking changes, open a new versioned endpoint/representation (e.g., `/v2/orders` or versioned media type) and keep v1 through an agreed deprecation window.

## 4. Spring Boot: Readers Tolerating Old Data While Validating Semantics

A consumer might receive both `OrderPlaced` payloads shown in section 2. The new decoder should default `currency=VND` **only for historical events whose old contract defined currency as VND**, never defaulting VND for new events declaring another currency.

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Set;
import org.springframework.stereotype.Component;

public record OrderPlaced(
        String eventId,
        String orderId,
        long amountMinor,
        String currency) {
}

@Component
public final class OrderPlacedDecoder {
    private static final Set<String> SUPPORTED = Set.of("VND", "USD");
    private final ObjectMapper mapper;

    public OrderPlacedDecoder(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public OrderPlaced decode(String rawJson) {
        try {
            JsonNode json = mapper.readTree(rawJson);
            if (json == null || !json.isObject()) {
                throw new IllegalArgumentException("Event must be a JSON object");
            }
            if (!"OrderPlaced".equals(text(json, "eventType"))) {
                throw new IllegalArgumentException("Unsupported eventType");
            }
            JsonNode amount = json.get("amountMinor");
            if (amount == null || !amount.isIntegralNumber()
                    || !amount.canConvertToLong()) {
                throw new IllegalArgumentException("amountMinor must be a long");
            }
            // Default VND only when field is absent, matching historical events.
            // Present but null currency field is a contract violation.
            String currency = json.has("currency")
                    ? text(json, "currency") : "VND";
            if (!SUPPORTED.contains(currency)) {
                throw new IllegalArgumentException("Unsupported currency");
            }
            return new OrderPlaced(
                    text(json, "eventId"), text(json, "orderId"),
                    amount.longValue(), currency);
        } catch (com.fasterxml.jackson.core.JsonProcessingException ex) {
            throw new IllegalArgumentException("Invalid JSON", ex);
        }
    }

    private static String text(JsonNode json, String field) {
        JsonNode value = json.get(field);
        if (value == null || !value.isTextual()
                || value.textValue().isBlank()) {
            throw new IllegalArgumentException("Missing or invalid: " + field);
        }
        return value.textValue();
    }
}
~~~

Place each `public` type in its own Java file in real codebases; they are combined here for illustration. In production, add payload size limits, amount bounds/normalization, currency code standards per contract, and `eventId` deduplication. For monetary data, never compute with `double` or implicitly mix USD/VND integers.

Because the decoder supports both VND and USD, **emit USD events only after all old consumers are upgraded or detached from that topic**. If earlier emission is needed, keep a v1 topic strictly VND and publish v2 representations on a separate topic/API or compatibility adapter without altering old semantics.

### The Version Field Trap

`schemaVersion` helps route decoders/upcasters, but does not ensure compatibility on its own. If consumer N has a switch accepting only `schemaVersion=1`, producer N+1 bumping `schemaVersion=2` just for adding an optional field will break consumer N immediately even when JSON remains readable. Define a **versioning policy**: does version increment on every representation change or only on breaking changes? Test real old readers before enabling new writers.

## 5. Event Schemas: Kafka, RabbitMQ, Avro, Protobuf, and Schema Registry

Event-driven integrations serve **multiple simultaneous consumer versions** alongside **historical events sitting in logs, retry topics, or DLTs**. HTTP clients usually see live responses; Kafka consumers may read records written months earlier. Compatibility policies must cover both *online rollouts* and *long-term replay*.

### 5.1. Controlling Schemas with a Registry

With Kafka using Avro, Protobuf, or JSON Schema, a **schema registry** can enforce compatibility rules between *new schemas and registered versions* per policy; exact details depend on registry vendor and serializer.

Common modes in Confluent Schema Registry:

| Mode | Guarantee in Registry Terms | What Must Still Be Tested |
| --- | --- | --- |
| `BACKWARD` | Reader using **new schema** reads data written with **immediately prior schema** | New consumer receiving old records |
| `FORWARD` | Reader using **old schema** reads data written with **new schema** | Old consumer receiving new records |
| `FULL` | Combines `BACKWARD` and `FORWARD` for adjacent versions | N and N+1 readers/writers |
| `BACKWARD_TRANSITIVE` | New reader reads data from **all previous schemas** in subject | Replaying historical events into new consumers |
| `FORWARD_TRANSITIVE` | All old readers read data written with new schema | New producer serving multiple legacy consumers |
| `FULL_TRANSITIVE` | Bidirectional compatibility across **every historical schema in subject** | Wide mixed-version fleets and long replays |
| `NONE` | No compatibility checks in registry | Use only when another governance mechanism replaces it |

These are **schema registry** definitions; they do not guarantee consumers are deployed on the right version, prove business semantics match, or validate HTTP/DB contracts. Non-transitive `BACKWARD` checks only the immediately preceding version, so a chain of individually valid steps can still break a new reader on very old records.

**Deployment ordering rule of thumb:** under standard schema evolution, backward compatibility supports **upgrading consumers before producers**; forward compatibility supports **upgrading producers before consumers** when old readers truly interpret the new data accurately. In rolling updates, prefer new readers tolerating old data, enabling new data emission only once all live readers handle it correctly. Across many independent producers/consumers, `FULL` or `FULL_TRANSITIVE` helps at higher development overhead.

### 5.2. Avro: Adding Fields with Defaults

Abbreviated Avro schema v1:

~~~json
{
  "type": "record",
  "name": "OrderPlaced",
  "namespace": "example.integration.events",
  "fields": [
    {"name": "eventId", "type": "string"},
    {"name": "orderId", "type": "string"},
    {"name": "amountMinor", "type": "long"}
  ]
}
~~~

Schema v2 adds a field:

~~~json
{
  "type": "record",
  "name": "OrderPlaced",
  "namespace": "example.integration.events",
  "fields": [
    {"name": "eventId", "type": "string"},
    {"name": "orderId", "type": "string"},
    {"name": "amountMinor", "type": "long"},
    {"name": "currency", "type": "string", "default": "VND"}
  ]
}
~~~

Under Avro schema resolution, **reader v2** fills default `"VND"` when reading v1 records lacking `currency`. **Reader v1** normally ignores the `currency` field emitted by writer v2. As shown in section 2, if writer v2 emits USD, reader v1 ignores `currency` and **miscomputes money**. A registry validates structural compatibility but cannot catch that semantic bug.

For nullable fields, Avro schemas usually declare a union with matching default:

~~~json
{
  "name": "externalReference",
  "type": ["null", "string"],
  "default": null
}
~~~

Provide a `default` on new fields when new readers must read old data; when removing an old field, check defaults/aliases in both forward and backward directions. Changing enum symbols, numeric types, logical types (decimal scale, timestamp units), record names, or field meanings can break compatibility depending on schema/serializer rules. Never rely on a naive "adding a field = safe" checklist across every format.

### 5.3. Protobuf: Field Numbers Are the Identity

In Protobuf, **field numbers** define wire identity; renaming a field while keeping its number does not magically keep semantics intact. Example:

~~~proto
syntax = "proto3";

package example.integration.events;

message OrderPlaced {
  string event_id = 1;
  string order_id = 2;
  int64 amount_minor = 3;
  optional string currency = 4;
}
~~~

When removing a field, **never reuse its field number** for a new meaning. Mark retired numbers/names `reserved` in the new schema:

~~~proto
message OrderPlacedLegacyMigration {
  reserved 5;
  reserved "old_internal_code";
  string event_id = 1;
  string order_id = 2;
  int64 amount_minor = 3;
  optional string currency = 4;
}
~~~

Protobuf v3 has presence/default rules and unknown-field behavior you must verify per language/runtime. Adding enum values or changing wire types can send unrecognized values to old code or misparse data. Changes to field numbers, repeated/singular, `oneof`, or `map` require verifying both **Protobuf wire safety** and business semantics. Never test parsing only in Java and assume .NET, Go, or Node.js consumers behave identically.

### 5.4. Where Do Schema Ownership and Versions Live?

Keep schemas in a domain-owned repository/interface or access-controlled registry tying change approvals to producer–consumer contracts. Naming/versioning options include:

- **Schema ID** in wire format/headers (per serializer/registry); consumers look up the writer schema.
- **Event type + schema version** in envelopes or metadata for routing/upcasting and auditability.
- **Topic/queue versioning** when breaking semantics cannot share a stream (e.g., `orders.events.v2`).
- **HTTP path/media-type versioning** for clients unable to upgrade simultaneously.

Versioning is not an end in itself: spawning `v2` without deprecation policies, consumer inventories, retention rules, and replay migrations leaves two permanent integration paths that never get cleaned up.

### 5.5. Schemas in DLTs, Retry Queues, Outboxes, and Replays

Failed messages can carry:

1. Raw bytes written with an older serializer/schema.
2. Original Schema ID or headers.
3. Exception metadata attached by Spring Kafka/RabbitMQ.
4. Payloads transformed by a recoverer (potentially differing from the original).

An N+1 DLT consumer must never assume every record is JSON v2. Preserve/resolve writer schema, event type, and conversion rules. If Kafka long retention still holds v0 events, **v0 must still decode cleanly** or have a reliable migration/copy. Never purge old schemas from the registry or delete upcasters while retention/replay windows still allow historical records.

**Caution on replays:** replays keep the original `eventId`/idempotency key while adding `replayRunId`, `originalTopic`, and `originalOffset` in investigative metadata. If migration requires altering the payload, document explicitly whether it is a **new representation of the same event** or a **new corrective event**, avoiding unintended duplicates or ordering violations.

## 6. Shared Databases: Expand → Migrate → Contract

During rolling updates, two Spring Boot versions can query the **same database simultaneously**. Never deploy a breaking migration understood only by N+1 code. In particular, Flyway/Liquibase DDL often runs **before all N pods are replaced**.

### 6.1. Example: Splitting an Address Column

Initial schema:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    request_id VARCHAR(64) NOT NULL UNIQUE,
    shipping_address VARCHAR(400) NOT NULL,
    status VARCHAR(32) NOT NULL
);
~~~

N+1 wants `shipping_city` and `shipping_postal_code`. Instead of renaming `shipping_address` directly or adding two `NOT NULL` columns without defaults, split across releases.

~~~mermaid
flowchart LR
    A[Release N: reads/writes shipping_address]
    A --> B[EXPAND: add nullable columns]
    B --> C[N+1: dual-write, read fallback]
    C --> D[MIGRATE: batch backfill]
    D --> E[Verify all writers/readers and data]
    E --> F[N+2: switch source of truth via flag]
    F --> G[CONTRACT: drop old column only after rollback/replay window]
~~~

**Phase 1 – EXPAND**: additive migration:

~~~sql
-- V20261121_01__expand_shipping_columns.sql (PostgreSQL example)
ALTER TABLE orders
    ADD COLUMN shipping_city VARCHAR(120),
    ADD COLUMN shipping_postal_code VARCHAR(32);
~~~

With the old column and its semantics intact, pod N keeps working. Index creation, table locks, and DDL timings differ across PostgreSQL, MySQL, and SQL Server; never copy syntax blindly or assume instant DDL on huge tables. Version migrations via Flyway/Liquibase, coordinate single execution, and watch locks and replication lag.

**Phase 2 – MIXED READ/WRITE**: version N+1 writes **both representations** when accurate values are available; on read, use the new columns when populated and fall back per the old contract otherwise. Handle rows where pod N only wrote `shipping_address` during mixed execution. If city/postal code cannot be parsed reliably from free text, **never guess**: leave null, request enrichment, or flag records for remediation.

**Phase 3 – MIGRATE**: backfill historical rows in repeatable, idempotent batches. Track watermarks/progress, avoid long locks, read rows missing new columns from trusted data, and update conditionally. Example using externally verified data:

~~~sql
-- Update only when new data is absent; values pre-verified.
UPDATE orders
SET shipping_city = :verified_city,
    shipping_postal_code = :verified_postal_code
WHERE id = :order_id
  AND shipping_city IS NULL
  AND shipping_postal_code IS NULL;
~~~

While N pods are still writing `shipping_address` and N+1 treats the new columns as canonical, a one-shot backfill **is not enough**: run dual-write/compatibility logic, change capture, or repeated backfill passes until all old writers are gone and reconciliation completes.

**Phase 4 – CONTRACT**: only after proving no code, reports, ETLs, consumers, or replay jobs rely on `shipping_address`, drop the old column in a separate release:

~~~sql
-- Execute only after old code's rollback window expires.
ALTER TABLE orders DROP COLUMN shipping_address;
~~~

Dropping a column cannot be safely rolled back simply by redeploying the old JAR. Once contract migration runs, rolling back requires a designed forward-compatibility fix or dedicated data recovery; **never promise old code rollback remains possible**.

### 6.2. Code–Database Compatibility Matrix

| Code Version | Old Schema | Expanded Schema | Contracted Schema |
| --- | --- | --- | --- |
| **N** uses only `shipping_address` | OK | OK | **Broken**: column dropped |
| **N+1** dual-read/dual-write | May fail if code queries new columns | OK | May break if still writing old column |
| **N+2** uses new columns with fallback | Must not deploy before expand | OK | OK once all old-column references are gone |

Do not treat this table as a universal guarantee for every app; **test with real binaries and real schemas**. Even an "additive column" migration can break pod N if code uses positional `SELECT *` mapping, strict unknown-field checks, or column-order-dependent ETLs.

### 6.3. Compatibility When Changing Enums or Constraints

Adding `PAUSED` to order statuses can cause version N to:

- Fail mapping the DB value into a Java enum lacking `PAUSED`.
- Execute an unsafe `default` branch (e.g., treating unknown statuses as `CANCELLED`).
- Overwrite `status=RECEIVED` back onto the row because it doesn't understand the transition.

Strategy: deploy readers that handle/route unknown statuses cleanly **without emitting the new status yet**; once old readers are retired or guarded, toggle writers via feature flag. Before adding DB `CHECK` or `NOT NULL` constraints, confirm no remaining legacy writer emits violating values.

### 6.4. Migrations Do Not Replace Data Rollbacks

Data-transforming migrations can be irreversible—e.g., merging columns, normalizing values, or dropping fields. Distinguish:

- **Application rollback:** shift traffic back to binary N.
- **Config/feature-flag rollback:** disable emitting the new format while keeping binary N+1.
- **Schema rollback:** possible only for reversible migrations with safe backups and verified procedures.
- **Data compensation:** new business operations to repair data, not reversing `DROP COLUMN`.

A rollout plan without explicit rollback windows and stop points is incomplete, even if the migration tool reports success.

## 7. Sequencing Producer and Consumer Deployments When Multiple Versions Coexist

Event-stream changes often take more releases than single-service changes because producers and consumers evolve independently. A Kafka topic can serve multiple consumer groups; within **one consumer group**, partitions can be split between N and N+1 pods. Producers cannot dictate which pod version handles a given record during rolling updates.

### 7.1. Reader-First, Writer-Later Strategy

When adding `currency`:

1. **Inventory:** list every consumer of `orders.events`, including analytics, ETL, auditing, replay workers, and partners. Verify what versions/schemas they support.
2. **Register schema and test contracts:** run registry compatibility checks if used, plus semantic contract tests.
3. **Deploy reader N+1 first:** consumers accept N events without `currency` (defaulting VND per old contract) and N+1 events with `currency`. Producers still emit only VND.
4. **Monitor mixed deployment:** confirm N+1 instances process historical events cleanly; find lingering N instances or external consumer groups not yet updated.
5. **Enable writer N+1 afterward:** turn on multi-currency emission via feature flag only after no incompatible old readers remain; in some systems, use a new event type/topic instead of flipping a flag.
6. **Retain replay support:** keep N event decoders in new releases for the entire historical retention/replay window.
7. **Retire legacy format:** only after dependencies on old messages end and data migrations/retention policies complete.

~~~mermaid
sequenceDiagram
    participant Ops as Release pipeline
    participant P as Producer
    participant CN as Consumer N
    participant CNew as Consumer N+1
    participant B as Broker
    Ops->>CNew: Deploy reader supporting old + new schemas
    Note over CN,CNew: Coexist across groups or rolling updates
    P->>B: V1 / VND (new feature OFF)
    B-->>CN: V1
    B-->>CNew: V1
    Ops->>Ops: Verify inventory, DLT, and consumer lag
    Ops->>CN: Replace/retire old readers
    Ops->>P: Enable new writer when safe
    P->>B: V2 / USD (new feature ON)
    B-->>CNew: V2
~~~

**Why not enable the new writer the moment one N+1 consumer pod looks healthy?** Inside a consumer group, pod N may still own other partitions; external consumer groups may still run N everywhere. Once the writer emits USD, old readers can silently mis-account money without crashing.

### 7.2. When Is Producer-First Acceptable?

If the new contract is **proven forward-compatible** with every active old reader—for example, adding a purely optional descriptive field ignored by old logic—you may deploy the writer first. Still verify:

- Old decoders do not enable `FAIL_ON_UNKNOWN_PROPERTIES` or strict schemas that reject it.
- New fields do not alter existing field meanings or introduce enum values unknown to old code.
- Payloads remain under broker, registry, HTTP gateway, and compression size limits.
- Security policies, log masking, and storage/indexes do not rely on a fixed field set.

**There is no universal ordering rule for every schema.** Follow dependency order: whichever side understands both formats deploys first; whichever emits data not yet understood by the other activates afterward.

### 7.3. Versioned Topics or Dual-Publishing for Breaking Changes

When new semantics cannot translate cleanly back to old ones—e.g., replacing `OrderPlaced` with `OrderSettled` carrying different accounting semantics—consider:

~~~text
orders.events.v1  <--- producer compatibility adapter  <--- domain state
orders.events.v2  <--- producer v2                    <--- domain state
                         |
                     consumer v2
~~~

Dual-publishing carries costs: streams can diverge in timing, ordering, and partial failures. Drive both from a single **outbox/source-of-truth**, retain explicit idempotency keys, and reconcile both paths. Never issue two `KafkaTemplate.send()` calls and assume atomicity with the DB; use a transactional outbox, scoped broker producer transactions, or retry/reconciliation workflows.

When migrating consumers from v1 to v2, specify offset cutover points, snapshot/rehydration sources, and overlap handling so events are neither dropped nor double-consumed. If both event types represent the same business action, consumers must deduplicate **across both topics**, not just within one.

## 8. Other Integration Boundaries Must Also Be Compatible

### 8.1. Outbox, Inbox, and Idempotency During Transition

Reliable systems persist business transactions and outbox events in one DB transaction before async publishers emit to Kafka/RabbitMQ. During rolling deployments:

- Pod N writes v1 outbox payloads.
- Pod N+1 writes v2 outbox payloads.
- Publisher N or N+1 may poll the same table.
- Retry schedulers or DLT replays may republish v1 events **after main producers upgraded to v2**.

New publishers and consumers must decode/route legacy queued rows properly. Outbox rows should carry `eventId`, `eventType`, `schemaVersion` or schema ID, `aggregateId`, publish state, and creation time. Publishers must not silently transform v1→v2 if semantics change; any upcasting must be tested, idempotent, and audited.

Example inbox structure blocking duplicates:

~~~sql
CREATE TABLE consumed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

With PostgreSQL, handlers can run `INSERT ... ON CONFLICT DO NOTHING` in the same transaction as business updates and check inserted row count. If already processed, skip duplicate side effects. **Never** mark `consumed` before the business transaction commits and risk ending in a broken state; inbox writes and business updates share one transaction or a recoverable state machine.

For outbound partner HTTP calls, DB transactions do not wrap remote requests. If N+1 calls the partner and crashes before DB commit, N or N+1 may reprocess; rely on partner idempotency keys and reconciliation. Multi-version deployments do not change this rule.

### 8.2. Spring Integration: Message Headers, Channels, and Transformers

An `IntegrationFlow` can combine HTTP inbound, file adapters, transformers, routers, filters, JDBC handlers, and outbound brokers. Message headers like `contentType`, `correlationId`, `replyChannel`, and `errorChannel` carry contracts; renaming, changing types, or altering header serialization can break cross-broker or cross-app flows.

When new transformers handle multi-version data:

~~~mermaid
flowchart LR
    A[Inbound payload V1/V2] --> B{Identify schema}
    B --> C[Deserializer v1]
    B --> D[Deserializer v2]
    C --> E[Upcast to CanonicalOrder]
    D --> E
    E --> F[Validate business invariants]
    F --> G[Shared Router/Handler]
    G --> H[DB, HTTP, or broker]
    F -. Invalid .-> I[DLT / quarantine]
~~~

A helpful design pattern is a **canonical internal model** kept stable across upgrades. Edge readers/adapters parse and upcast; core business layers work against the internal model. When source schemas evolve, adapters change without rewriting the whole service.

However, a v2 message cannot always downgrade to a v1 model without losing critical information. If v2 introduces mandatory requirements unrepresentable in v1, block or route to a new flow—never "drop the field" and pretend success.

### 8.3. Cache Schemas and Cache Keys

Redis or shared caches accessed by N and N+1 pods can store serialized DTOs or objects in older versions. A deploy can fail even when HTTP, DB, and Kafka are compatible:

| Cache Storage Style | Risk | Protection |
| --- | --- | --- |
| Java native serialization | `serialVersionUID`, class/package renames, binary incompatibility | Avoid sharing unversioned binary serialized objects |
| Old/new JSON sharing one key | Old reader rejects unknown fields or misses defaults | Mixed-read support, TTLs, validation, compatibility tests |
| Semantic change under same key | Silently reads stale meaning with no exception | Versioned key namespaces or planned invalidation |
| Cached permissions/credentials | Uses stale authz data after deployment | Contracted TTLs/invalidation; avoid stale caches for security-critical checks |

For example, use `order:summary:v1:{id}` and `order:summary:v2:{id}` for breaking structural/semantic changes, backed by TTLs and warm-up/invalidation plans. Adding a `v2` suffix does not synchronize writes while old writers still populate `v1`; maintain consistency policies across both namespaces during transition.

### 8.4. TLS, Secrets, and Shared Configuration

Contract upgrades sometimes coincide with rotating mTLS certificates, CAs, or HTTP client OAuth scopes. During transition:

- Servers/gateways should accept **old and new** identities/certificates across the approved overlap window where PKI allows.
- New clients must trust the new CA **before** servers swap certificates; revoke old CAs once no dependent clients remain.
- Rotating secrets solely on new pods while old pods run causes intermittent failures.
- Never leak secrets into logs/canary tags; distinguish TLS/auth failures from schema/HTTP status errors.

Spring Boot configuration keys are operational contracts too. Renaming `app.partner.base-url` or feature flags only in N+1 code breaks pod N when both read a shared Config Server or Secret. Add new keys first, retain old keys during transition, and plan breaking config changes just like DB schemas.

## 9. Rolling, Canary, and Blue-Green: Choosing a Release Strategy

### 9.1. Rolling Deployment

Rolling updates replace N pods incrementally with N+1 pods while keeping the service online. Standard for Kubernetes Deployments, yet **requires N and N+1 to coexist safely** across databases, caches, APIs, and brokers.

Conceptual Deployment configuration example:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-api
spec:
  replicas: 4
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: order-api
  template:
    metadata:
      labels:
        app: order-api
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: app
          image: registry.example.internal/order-api:1.9.0
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 10
~~~

Assume Spring Boot Actuator configures Kubernetes probes and kubelet can access those endpoints. Replica counts, image registries, and timings are illustrative and must match real resources. `maxUnavailable: 0` maintains ready replica counts given sufficient cluster capacity, **yet does not guarantee** zero dropped requests during traffic shifts or replace connection draining and proper readiness checks.

For graceful shutdown:

- Stop admitting new work when pods begin terminating.
- Let active HTTP requests finish within termination grace.
- Stop Kafka/RabbitMQ listeners from polling/receiving and ack per policy; unconfirmed messages remain eligible for broker redelivery.
- Make DB/outbox writers idempotent when concurrent pods pick up tasks.
- Preserve trace and event correlation across N and N+1 hops.

In Spring Boot, configure `server.shutdown=graceful` and `spring.lifecycle.timeout-per-shutdown-phase` suited to your version and web server, aligned with orchestrator termination grace. Verify custom schedulers, thread pools, and message listeners separately; never assume one shutdown flag drains every adapter.

### 9.2. Canary: Routing Only a Fraction of Traffic to N+1

Canary sends a small percentage of traffic or **a specific message/tenant cohort** to the new version to validate behavior before expanding. For HTTP, ingress controllers or service meshes split request percentages. For Kafka, **you cannot route 5% of records to N+1 pods** just by running 5% N+1 replicas in one consumer group: partition assignments and key hashing dictate routing, not per-request load balancers.

Event-consumer canary techniques include:

- A separate **shadow consumer group** reading the same topic to verify parsing/transforms **without triggering side effects** (weigh read cost and PII rules).
- A **canary consumer group** dedicated to a test topic, test tenant, or designated data partition.
- **Feature flags** enabling new logic for a fixed set of business keys once old pods also handle the path safely.
- **Dual-run comparisons**: feeding identical sanitized inputs to old and new engines and comparing outputs without double-charging or double-shipping.

Canarying works only if metrics carry `application.version`/`deployment.track` labels separating N and N+1. Aggregate metrics can mask a high error rate on one new replica and create false confidence.

### 9.3. Blue-Green Deployment

Blue-green maintains two independent environments (`blue=N`, `green=N+1`) and flips traffic routing. It enables fast **routing** rollbacks, yet does not isolate databases or brokers if both share them.

**Critical constraint:** switching traffic back to blue is safe only if blue can still read database state, events, caches, and configs written by green. If green emitted new enums or a migration dropped an old column, flipping ingress back to blue widens the outage. Blue-green still requires **expand/compatibility** and feature gating—never skip schema evolution because you use blue-green.

### 9.4. Choosing by System Constraints

| Strategy | Advantage | Contract Risk |
| --- | --- | --- |
| Rolling | Low spare capacity overhead, automated by orchestrator | Demands mixed-version coexistence during rollout |
| Canary | Detects failures with small blast radius | Needs deliberate routing/splitting; tricky with broker partitions |
| Blue-green | Fast routing and code rollback | Shared DB/event schemas can still break blue |
| Shadow read / dual run | Compares old vs. new logic before turning on writers | Must prevent duplicate side effects; mind sensitive data |
| Feature flag | Decouples **binary deploy** from **behavior activation** | Must sync flag rules, safe defaults, and flag rollback |

### 9.5. Feature Flags Should Default Safe

Configuration example:

~~~yaml
# application.yml
integration:
  orders:
    enable-multi-currency-events: false
    read-v1-events: true
    write-legacy-shipping-address: true
~~~

Meaning:

| Flag | When `false` / `true` | When to Change |
| --- | --- | --- |
| `enable-multi-currency-events` | `false`: emit only compatible VND; `true`: may emit USD | Enable only after every relevant consumer understands currency |
| `read-v1-events` | `true`: keeps legacy decoder active | Disable only after replay/retention horizons expire per contract |
| `write-legacy-shipping-address` | `true`: continues dual-writes | Disable only when zero N readers or rollback needs remain |

These are **custom application properties**, not built-in Spring Boot flags. Bind via `@ConfigurationProperties` and document whether flags load once at startup or refresh dynamically. Never flip a flag simply because "one N+1 pod reported ready."

## 10. Testing Compatibility Before Release

### 10.1. Test a Version Matrix, Not Just N+1 Unit Tests

A release pipeline should verify three layers:

1. **Schema/static:** parse/validate Avro/Protobuf/JSON Schema, Schema Registry compatibility rules, OpenAPI/contract diffs, and DB migration linters.
2. **Behavioral contract:** execute real N and N+1 DTO/reader binaries against N and N+1 writer payloads—asserting business outcomes, not just deserialization.
3. **Deployment/integration:** run both versions side by side against expanded DBs, broker/HTTP test doubles, restarts/rollbacks/replays, and fault injection.

Example test matrix for `OrderPlaced`:

| Test Case | Producer | Consumer | Data | Pass Criterion |
| --- | --- | --- | --- | --- |
| Baseline | N | N | VND, no `currency` | Legacy outcome accurate |
| Backward | N | N+1 | No `currency` | N+1 infers VND per contract without error |
| Forward structural | N+1 | N | `currency=VND` | N succeeds without error and computes accurately |
| Breaking semantic | N+1 | N | `currency=USD` | **Forbidden in live traffic** while N lives; test demonstrates risk |
| New normal | N+1 | N+1 | `currency=USD` | Computes currency units accurately |
| Historical replay | N-2 | N+1 | Older schema missing other fields | Upcaster handles cleanly or routes explicitly to quarantine |
| Poison event | N/N+1 | N+1 | Wrong type, missing `eventId` | Rejects/DLTs with reason, zero side effects |

**Crucial point:** a consumer can deserialize USD JSON without throwing yet compute the wrong monetary value. Assertions must verify **currency units, amounts, idempotency, DB state, and emitted HTTP calls**, not merely `assertDoesNotThrow`.

### 10.2. HTTP Contract Tests

For HTTP, use Spring Cloud Contract, Pact, WireMock/MockWebServer, or OpenAPI-based tests. Pin **client N's expectations** against provider N+1, and test client N+1 against provider N if rolling updates allow that pairing.

Scenarios to verify:

- Client N sends requests without `shippingCity`; server N+1 accepts and processes per legacy contract.
- Client N receives responses containing new optional fields without decoder failures.
- Server N+1 returns `409` on duplicate `requestId` with semantics client N understands.
- Client N+1 never sends v2-only calls to an N server still receiving traffic (or enforces route/feature gating).
- Tokens/mTLS identities for both clients stay trusted across the overlap window.

Consumer-driven contract tests do not replace runtime network/TLS or database migration tests. For third parties lacking contract pipelines, use partner sandboxes, recorded response fixtures, and closely monitored canaries.

### 10.3. Database Migration Integration Tests

Use Testcontainers matching your real DB engine (PostgreSQL/MySQL/MongoDB) to run:

~~~text
DB V0 + binary N
  -> run EXPAND migration
  -> run binaries N and N+1 simultaneously
  -> N writes legacy records, N+1 reads/writes new records
  -> run batch backfill repeatedly
  -> restart and roll back code to N on the expanded schema
  -> assert zero data loss and zero SQL errors
  -> only after rollback window, test CONTRACT migration separately
~~~

Assert invariants such as row counts, unique request IDs, amounts, statuses, and alignment between old and new columns. Re-run backfills to confirm idempotency. For large tables, test with realistic row volumes to measure lock durations, index builds, and replication lag. Never assume "migration applied" equals "compatible."

### 10.4. Broker Tests and Replays

- Kafka: have producers N and N+1 publish to a test topic; run consumers N/N+1 in separate groups reading both, verifying schema IDs, headers, and offsets. Also test mixed N/N+1 pods inside one rolling consumer group.
- RabbitMQ: test queues, exchanges, routing keys, message properties/headers, serializers, and DLQ behavior when old decoders meet new messages.
- Spring Integration: assert payloads and headers on channels after transformers/routers; ensure `errorChannel` never swallows unparseable schemas.
- Outbox/inbox: replaying an event causes repeated reads without duplicating DB/HTTP side effects.
- DLT replay: run stored historical fixtures verifying compatible converters, audit trails, and error-threshold stops.

### 10.5. CI/CD Release Gates

A trustworthy pipeline blocks rollout if:

- New schemas violate registry policy or introduce unapproved/unplanned semantic shifts.
- Consumer-driven contracts for still-supported clients break.
- DB migrations break running binary N or lack backfill/rollback plans.
- Historical golden-fixture messages fail decoding in consumer N+1.
- Metrics/alerts cannot separate N from N+1 during canarying.
- Feature activation/rollback plans and downstream readiness checks are missing.

For approved breaking changes, gates should enforce **versioned endpoints/topics and deprecation contracts** rather than waiving failing checks.

## 11. Observing Mixed Versions and Making Rollback Decisions

A rollout can pass health checks while corrupting data. Readiness only confirms an instance passes probe criteria; it never proves old consumers understand new schemas or HTTP semantics remain intact. Monitor **business-effect metrics**.

### 11.1. Recommended Metrics and Logs

| Metric / Signal | Meaning | Critical Breakdown |
| --- | --- | --- |
| `integration_messages_total{service,version,result}` | Message processing success/failure rate | Separate reader N vs. N+1 |
| `integration_schema_decode_failures_total{event_type,writer_schema}` | Decode failures by writer schema | Pinpoint incompatible old/new messages |
| `integration_contract_rejections_total{code}` | Validation/semantic rejections | Distinguish bad data from infra outages |
| `http_server_requests_seconds{version,status}` | API error rates and latency during canary | Compare N and N+1 against baseline |
| `http_client_requests_seconds{remote_service,status}` | Outbound errors by contract/timeout/auth | Never lump `409` with `503` |
| `broker_consumer_lag{group}` | Kafka backlog during listener swaps | Old vs. new groups, partitions, and schema failures |
| `dead_letter_backlog{type}` | Quarantined message counts | Schema incompatibility vs. mapping vs. downstream errors |
| `outbox_oldest_unpublished_seconds` | Age of unpublished outbox events | Verify publisher N+1 reads N payloads cleanly |
| `database_migration_progress{phase}` | Backfill/verification progress | Catch remaining nulls and dual-write drift |
| `idempotency_duplicate_suppressed_total` | Suppressed duplicate executions | Abnormal spikes after rollout/rollback |
| `business_reconciliation_mismatch_total` | Mismatched amounts or side effects | Catch silent semantic errors even when parsing succeeds |

Metric names above are **implementation suggestions**, not guaranteed built-in Spring Boot/Micrometer meters. Tags like `service`, `application.version`, `eventType`, and normalized error codes help, while avoiding `requestId`, `eventId`, emails, customer IDs, raw payloads, or exception strings due to cardinality and PII. Store correlation IDs in access-controlled logs/traces with proper retention.

### 11.2. Business-Outcome Canary Gates

Example criteria before advancing a canary from 5% to 25%:

- Zero new **schema decode errors** over baseline across a representative traffic window.
- HTTP 5xx, timeouts, and P95/P99 latency stay within agreed SLO/error budgets.
- Kafka DLT / RabbitMQ DLQ rates do not climb on v1/v2 messages.
- Zero currency/amount mismatches, order status drift, or count discrepancies in reconciliation.
- Zero failed migrations, prolonged locks, or steadily climbing outbox backlogs.
- Independent consumer groups and external partners confirm compatibility.
- Operators can toggle off the new writer flag and halt rollout within the same shift.

Exact thresholds must match baseline traffic and business SLOs rather than arbitrary global constants. For rare high-risk events (refunds, cancellations), 5% live traffic might miss them entirely; test with dedicated fixtures and extend observation windows.

### 11.3. When Code Rollback Is Not Enough

Suppose N+1 already:

1. Wrote status `PAUSED` into the database.
2. Emitted `OrderPlaced(currency=USD)` to the shared topic.
3. Dropped column `shipping_address`.

Rolling all pods back to N causes N to fail mapping `PAUSED`, miscompute USD, and throw SQL errors. At that point, routing/code rollback is **not safe**.

Rollback capability must be engineered **before release**:

- Keep the DB in the expanded schema throughout the rollback window.
- Withhold new semantics until incompatible readers are gone.
- Disable new writers via feature flags without forcing full downtime.
- Retain recovery metadata/data for any irreversible transformations.
- Have compensation and reconciliation procedures for external side effects.

Once past a point of no return (an irreversible change), recovery requires a **roll-forward fix**, compatible hotfix, or controlled data restore/compensation—never claim "a single Kubernetes rollback command fixes everything."

## 12. Sample Release Runbook: Upgrading from N to N+1

### 12.1. Before the Deployment Window

1. **Lock contracts:** map N and N+1 writers/readers across HTTP, events, DB, caches, SSL, and config.
2. **Inventory every consumer:** include external consumer groups, batch jobs, CDC, BI/reporting, outbox publishers, and replay workers.
3. **Set compatibility policies:** registry mode (often transitive for long histories), OpenAPI/contract tests, and deprecation timelines.
4. **Mark irreversible boundaries:** `DROP COLUMN`, new enum writes, multi-currency emission, state-machine changes.
5. **Prepare observability:** version-split metrics, alerts, dashboards covering backlogs, errors, DLT, and business reconciliation.
6. **Verify recovery paths:** flag kill-switches, traffic flips, code rollback on expanded DB, stopping new producers, and decision authority.

### 12.2. Expand Phase

| Step | Action | Proceed Condition |
| --- | --- | --- |
| A | Run **additive** migration (nullable columns, online indexes) | Code N reads/writes normally |
| B | Register new schema and run compatibility checks | Schema/semantic tests pass |
| C | Deploy N+1 consumers/HTTP servers reading both v1/v2 | Zero increase in decode/contract errors |
| D | Keep new writers **OFF**; old producers emit legacy format | All live readers are compatible |
| E | Enable DB dual-read/dual-write behind feature gate | Old/new columns consistent; old pods error-free |
| F | Run batch backfill and reconcile | Zero unmarked missing data |

Before enabling new producers, require **concrete evidence** rather than "N+1 is deployed": pod version tables, consumer group statuses, partner confirmations, and v1/v2 smoke tests. While N still runs, new events must stay within semantics N interprets safely.

### 12.3. Activate Phase

1. Enable new behavior partially via flag/canary on a well-defined traffic slice.
2. Monitor schema errors, DLT, consumer lag, API latency, outbox backlog, and business invariants.
3. Step up canary percentages incrementally, verifying both live data and historical events at each tier.
4. Once every relevant reader supports and has verified the change, let producers emit new semantics.
5. Observe long enough to cover replays, schedulers, batch/ETL, and long-lived records—not just a few minutes post-deploy.

### 12.4. Contract Phase

Once the rollback window closes and zero old consumers remain:

- Remove obsolete feature flags via tested cleanup releases.
- Run contract migrations in a separate release (e.g., `DROP COLUMN`) with dedicated backup/restore plans.
- Stop dual-publishing/dual-writing once zero readers need legacy formats.
- Update API deprecation notices, schema registry lifecycles, producer/consumer docs, and replay playbooks.
- Retain historical upcasters/decoders as long as valid old records remain replayable.
- Remove transition-only metrics/checks **only after** sustained stability is proven.

Never bundle **expand, new-semantic activation, and destructive contract** into one release—recovering from failures becomes vastly harder.

### 12.5. Go/No-Go and Stop Actions Table

| Signal | Immediate Action | Roll Back to Binary N? |
| --- | --- | --- |
| Decode errors spike right after enabling new writer | **Turn off writer flag**, halt rollout, hunt down old consumers | Only if N still reads already-emitted records |
| Expand migration ran, N+1 code fails | Halt rollout, inspect schema bugs; leave schema expanded | Usually yes if tested |
| Column dropped while N still uses it | Stop changes; apply controlled roll-forward fix/restore | **No** simple rollback to N |
| DLT spikes on historical messages | Keep messages; fix/enable upcaster or schema decoder | Do not replay before fixing |
| Business mismatch without exceptions | Halt new emission, isolate bad source, reconcile | Never blind-rollback while new data exists |
| Partner HTTP rejects new TLS/permissions | Pause cert/auth rollout, restore overlapping trust safely | Depends on cert/secret compatibility with N |
| Consumer lag climbs post-upgrade | Check throughput, deserializers, partition balance | Roll back only if already-received data stays compatible |

Runbooks must assign clear owners for DB migrations, schema registry, producer flags, consumer fleets, external partners, and rollback calls. Under change-approval workflows, record test evidence and gate timestamps before advancing stages.

## 13. Common Mistakes and Self-Check Questions

### Mistakes to Avoid

1. **"Schema registry says PASS so business logic is safe."** Registries verify wire schemas, not whether old consumers treat USD as VND.
2. **"It's just one service, so concurrent deployment is easy."** Databases, caches, outboxes, cron jobs, and historical messages are versioned readers/writers too.
3. **"Adding a field is always backward/forward compatible."** Depends on decoders, defaults, required/optional rules, enums, semantics, and read/write direction.
4. **"Flyway migrated cleanly, so rollback works."** Destructive migrations and data transforms are not reversed by redeploying an old JAR.
5. **"Blue-green eliminates mixed versions."** HTTP traffic may split cleanly, yet shared DBs and brokers still serve green-written data to blue.
6. **"New Kafka consumers look healthy, so everyone is ready."** External consumer groups, analytics, batch jobs, or replay workers may still lag behind.
7. **"Replay is just re-sending messages."** Must preserve `eventId`, audit runs, rate-limit, enforce ordering, and guarantee idempotency.
8. **"Canary passed, drop the old column now."** Batch jobs, reports, ETLs, and rollback windows may not have been tested yet.

### Self-Check Questions

- If reader N+1 reads payload N but reader N fails on payload N+1, does the contract have backward, forward, or full compatibility?
- Why can adding `currency` with default `VND` to `OrderPlaced` still be a breaking change once producers emit `USD`?
- Why is `BACKWARD` not the same as `BACKWARD_TRANSITIVE` in Schema Registry?
- If N and N+1 pods run together after `ALTER TABLE ADD COLUMN`, under what conditions can the migration still cause errors?
- After enabling a new producer, is flipping blue-green traffic back to old pods always safe?
- If 95% of a Kafka consumer group upgraded to N+1, is it safe to emit new events? Who else might be reading?
- When a legacy N outbox row publishes after all producers upgraded to N+1, what capability must consumers retain?
- Why must feature flags, idempotency, compatibility tests, and monitoring be designed together?

**Conclusion:** Safe multi-version deployment is a discipline of **reader/writer compatibility and change sequencing**, not merely running multiple pods. In Spring Boot Integration, a reliable rollout evaluates HTTP contracts, event schemas, databases, caches, configuration, and replay data **within the same version matrix**. The effective pattern is **expand first, upgrade readers first, activate writers later, observe and reconcile, and contract only last**.

## References

- [Confluent Schema Registry — Schema Evolution and Compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html)
- [Apache Avro — Schema Resolution and Defaults](https://avro.apache.org/docs/current/specification/#schema-resolution)
- [Protocol Buffers — Updating a Message Type](https://protobuf.dev/programming-guides/proto3/#updating)
- [Protocol Buffers — Proto Best Practices](https://protobuf.dev/best-practices/dos-donts/)
- [Spring Boot Reference — Database Initialization and Migration](https://docs.spring.io/spring-boot/reference/how-to/data-initialization.html)
- [Flyway Documentation — Migrations](https://documentation.red-gate.com/fd/migrations-184127470.html)
- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/)
- [Spring Kafka Reference — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Integration Reference — Message Transformation](https://docs.spring.io/spring-integration/reference/transformer.html)
- [Kubernetes — Deployments and Rolling Updates](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Kubernetes — Container Lifecycle / Termination](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/)

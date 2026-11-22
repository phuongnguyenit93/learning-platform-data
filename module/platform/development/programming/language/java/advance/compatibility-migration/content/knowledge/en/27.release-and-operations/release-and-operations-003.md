# Running Old and New Versions Concurrently with a Shared Data Contract

A Java or framework upgrade is rarely deployed across the entire system simultaneously. During a **rolling deployment**, **canary release**, or **blue–green deployment**, multiple instances of the old and new versions may simultaneously serve traffic, read/write the database, exchange messages, and share caches. If the new version changes a data format that the old version does not understand, the system may operate normally for the first few minutes and then fail when a request lands on an old instance, when a message is retried, or when a rollback is needed.

To avoid that scenario, both versions must share a **shared data contract** during their **coexistence period**. The contract does not necessarily require both versions to use the same Java classes or the same internal database model. It requires that both versions can **produce, read, and accurately interpret the data the other version may emit** within the committed deployment window, while preserving business invariants and recoverability.

This lesson belongs to the **Release and Operations** chapter of the **Java Advance Compatibility Migration** module. The focus is designing a Java/JDK/framework upgrade where **old and new can run concurrently safely**, covering API/message/schema contracts, database expand–migrate–contract, traffic routing, contract testing, monitoring, and rollback.

## 1. Learning Objectives

After this lesson, learners can:

- Explain why rolling/canary/blue–green deployments create a **mixed-version** state.
- Distinguish compatibility when **reading old data** versus **reading new data**; do not equate them.
- Define a shared data contract across schema, types, semantics, defaults, validation, and protocol versions.
- Design evolutionary schema changes: adding optional fields, deferring required fields, preserving field IDs, and handling unknown values.
- Apply the **expand → migrate → contract** strategy for databases accessed concurrently by multiple versions.
- Avoid pitfalls in dual-write, cache serialization, session affinity, shadow traffic causing side effects, and message consumer incompatibility.
- Write a bidirectional producer–consumer test matrix and verify old/new combinations.
- Establish readiness, canary metrics, feature flags, rollback gates, and procedures for removing temporary compatibility.
- Connect mixed-version risks to changes in the JDK, Jakarta, JSON frameworks, ORM, JDBC, timezone/charset, and serialization.

## 2. Why Do Two Versions Appear Simultaneously in a System?

### 2.1. Rolling Deployment

A cluster has four instances, replacing old instances with new ones one by one:

```text
Before deploy:  [OLD] [OLD] [OLD] [OLD]
Step 1:         [NEW] [OLD] [OLD] [OLD]
Step 2:         [NEW] [NEW] [OLD] [OLD]
Step 3:         [NEW] [NEW] [NEW] [OLD]
After deploy:   [NEW] [NEW] [NEW] [NEW]
```

During steps 1–3, requests can hit both old and new. If both versions also share a database, queue, or cache, the impact is not limited to traffic routing but also affects **data shared over time**.

### 2.2. Canary Release

A small portion of traffic is shifted to the new version:

```text
                  +----------------> OLD (95%)
Client -> Router -|
                  +----------------> NEW (5%)
```

Canary aims to measure compatibility before scaling up. However, if NEW writes data that OLD cannot read, even **5% of requests going through NEW** can break the 95% of OLD instances when they read that same data.

### 2.3. Blue–Green Deployment

There are two application environments:

```text
Blue:  OLD instances
Green: NEW instances
```

Traffic can be switched via a router or DNS. Yet both environments may still share a database/message broker. In that case, blue–green **does not mean data is isolated**.

If using two separate databases, synchronization and reconciliation must be solved before switching; do not assume dual-writing to two places is a safe deployment pattern.

### 2.4. Rollback Also Creates Mixed-Version States

A rollout reaches 80% NEW, detects an error, and shifts traffic back to OLD. At this point, **NEW may have already written new data** to the database/queue/cache. OLD must be able to read that data, or the rollout cannot actually be rolled back.

Therefore, the critical question is not only "Can NEW read old data?" but also:

> **"After NEW writes data, does OLD continue to work correctly if traffic reverts?"**

That is the core condition of a rollback-safe migration.

## 3. What Is a Shared Data Contract?

A data contract is the set of rules that producers, consumers, and storage layers collectively follow. It encompasses more than a single JSON Schema file or database table.

A contract should describe:

| Component | Example Content to Agree On |
| --- | --- |
| Identifiers | `orderId` is a stable string, never reused for another order. |
| Data types | `amountMinor` is an integer representing the smallest currency unit, not floating point. |
| Required/optional | `currency` is optional during the concurrent phase; its default is clearly defined. |
| Null and missing | Do an absent field, `null`, and an empty string mean the same thing or not? |
| Enums and states | Can new values be safely handled by old consumers? |
| Timestamps | Timestamps are UTC/offset-aware; precision and timezone are specified. |
| Charset | Text/wire formats standardize on UTF-8 where applicable to the protocol. |
| Business constraints | No double charging; valid order status transitions. |
| Schema evolution rules | Additive first; do not delete/rename while old consumers still exist. |
| Protocol/version | Is a version needed in headers/envelopes/topics/endpoints? |
| Ordering/idempotency | Events have stable IDs; retries/replays do not cause duplicate effects. |
| Error semantics | What does a consumer do upon encountering an unknown field/enum? |
| Compatibility bounds | Commitment to N and N−1 or more versions; for how long? |

The contract must be reflected in **actual consumer behavior**. Having a "clean" schema on paper while OLD's serializer throws an exception on a new field is still incompatible.

## 4. Two Compatibility Directions: Backward and Forward

### 4.1. Definitions by Reader and Writer

During migration, to avoid terminology debates, explicitly identify **who writes and who reads**:

- **NEW reader reads OLD writer:** existing data or data continued to be produced by OLD must be understood by NEW.
- **OLD reader reads NEW writer:** data produced by NEW during rollout/rollback must be understood by OLD.

Diagram:

```text
                OLD writer                 NEW writer
                     |                          |
                     v                          v
                Data schema V1             Data schema V2
                     |                          |
          +----------+-----------+  +-----------+----------+
          |                      |  |                      |
          v                      v  v                      v
      OLD reader              NEW reader              OLD reader
      (baseline)           (backward read)          (forward read)
```

In common schema-registry systems, **backward compatibility** typically refers to a new reader reading data produced by an old writer, whereas **forward compatibility** refers to an old reader reading data produced by a new writer. Some systems use different rules or terminology; always check the definition in the schema registry/protocol you are using.

### 4.2. Four Key Combinations

| Producer | Consumer | Meaning |
| --- | --- | --- |
| OLD | OLD | Baseline; must be stable before upgrading. |
| OLD | NEW | NEW can read historical data and old producers. |
| NEW | OLD | OLD continues working when NEW starts emitting data; critical for rollback. |
| NEW | NEW | Target functionality works properly. |

A build that tests only NEW–NEW is insufficient for a mixed-version release.

### 4.3. Being Able to Parse Does Not Mean Interpreting Correctly

For example, OLD does not crash when reading a new event:

```json
{
  "orderId": "O-123",
  "status": "PARTIALLY_REFUNDED"
}
```

However, if OLD only knows `NEW`, `PAID`, and `CANCELLED`, it might:

- Throw an exception while deserializing the enum.
- Assign an unsafe default.
- Misinterpret it as a cancelled order.
- Drop the event, causing inconsistent balances.

Therefore, **"the parser does not crash" is only the first condition**. You must also ensure consumers behave properly with values that the new writer may emit.

## 5. Safe Schema Evolution Rules During the Concurrent Phase

### 5.1. Prefer Additive Changes

Initial contract:

```json
{
  "orderId": "O-123",
  "status": "PAID"
}
```

The new version wants to add currency:

```json
{
  "orderId": "O-123",
  "status": "PAID",
  "currency": "VND"
}
```

This change **can be compatible** if:

1. NEW accepts old payloads missing `currency` with valid fallback semantics.
2. OLD accepts or ignores unknown fields per the contract.
3. NEW does not emit a value that OLD would misinterpret.
4. All actual encode/decode paths, including caches/messages, are tested.

Do not claim "adding a JSON field is always backward compatible". For instance, a Jackson POJO may fail on unknown properties if configuration or annotations do not allow ignoring them.

### 5.2. Do Not Add Required Fields Immediately

If NEW requires:

```json
{
  "orderId": "O-123",
  "status": "PAID",
  "currency": "VND"
}
```

and the new validator marks `currency` as mandatory, records created by OLD will still lack that field. NEW readers must tolerate old data during the transition period, or a reliable backfill must happen **before** enforcing the requirement.

A safer progression:

1. Add the field as optional/nullable.
2. NEW readers handle both the presence and absence of the field.
3. OLD readers are tested against the new field.
4. NEW writers begin writing the new field within contract rules.
5. Backfill historical data.
6. Only after no OLD writers remain and data is complete should you consider making the field required.

### 5.3. Distinguish Missing, Null, and Empty

Three payloads may not share the same meaning:

```json
{}
```

```json
{"customerName": null}
```

```json
{"customerName": ""}
```

One mapper might apply a default when the field is absent while keeping `null` when present; another validator might reject both null and empty. When changing Jackson/JSON-B/frameworks, test each case and align semantics.

### 5.4. Do Not Change Data Types in Place

It is unsafe when a field that used to be an integer:

```json
{"amount": 120000}
```

becomes an object:

```json
{"amount": {"value": 120000, "currency": "VND"}}
```

OLD parsers may fail to read it. The usual solution is to **add a new field** and keep the old field during the transition window:

```json
{
  "amount": 120000,
  "amountDetail": {
    "minorUnits": 120000,
    "currency": "VND"
  }
}
```

Explicitly define which field is the primary source while both coexist, and how inconsistencies are detected. Do not let two fields be written independently without synchronization rules.

### 5.5. Renaming a Field Must Go Through a Dual-Read Phase

Renaming `customerName` to `displayName` by immediately removing the old field is a breaking change.

The progression can be:

```text
V1:  customerName
       |
       v
V2:  reader understands both customerName and displayName
     writer still writes customerName (or writes both when safe)
       |
       v
V3:  all readers understand displayName
     writer starts using displayName as canonical
       |
       v
V4:  after rollback window ends, drop customerName
```

**Warning:** "dual-writing" two fields in the same record must keep them consistent. If an OLD writer only updates the old field, a NEW reader prioritizing the new field may see stale values. There must be a clear phase establishing the authoritative data source.

### 5.6. New Enum Values Are Potential Breaking Changes

If NEW adds the `ON_HOLD` status, OLD may not know how to process it. Solutions depend on business rules:

- Defer emitting the new value until OLD consumers have left the system.
- Have readers support unknown values and route them to quarantine.
- Use a separate versioned event/endpoint.
- Design a **safe** fallback state if the contract allows it.

Do not silently map unknown values to `PAID`, `SUCCESS`, or a business state with side effects just to avoid an exception.

## 6. JSON Contracts with Java: Reading Old and New Versions

### 6.1. Models Independent of Internal Classes

Suppose the wire contract has:

```json
{
  "orderId": "O-123",
  "status": "PAID",
  "currency": "VND"
}
```

NEW may receive payloads from OLD without `currency`. A Java example using Jackson `JsonNode`, without relying on direct enum deserialization:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

public final class OrderWireReader {
    private static final ObjectMapper MAPPER = new ObjectMapper();

    public static OrderMessage read(String json) throws Exception {
        JsonNode root = MAPPER.readTree(json);

        JsonNode idNode = root.get("orderId");
        JsonNode statusNode = root.get("status");

        if (idNode == null || !idNode.isTextual()
                || statusNode == null || !statusNode.isTextual()) {
            throw new IllegalArgumentException(
                    "orderId/status missing or invalid");
        }

        String id = idNode.asText();
        String status = statusNode.asText();

        // V1 lacks currency; the fallback value is only valid
        // if the old contract guaranteed all orders are in VND.
        JsonNode currencyNode = root.get("currency");
        String currency;

        if (currencyNode == null || currencyNode.isNull()) {
            currency = "VND";
        } else if (currencyNode.isTextual()) {
            currency = currencyNode.asText();
        } else {
            throw new IllegalArgumentException("Invalid currency");
        }

        return new OrderMessage(id, status, currency);
    }

    public static final class OrderMessage {
        public final String orderId;
        public final String status;
        public final String currency;

        public OrderMessage(String orderId, String status, String currency) {
            this.orderId = orderId;
            this.status = status;
            this.currency = currency;
        }
    }
}
```

This is an illustrative example of reading V1/V2 payloads under a very specific contract. **Defaulting to `VND` is only correct if historical data genuinely always used VND**; otherwise, this fallback introduces currency errors and must be replaced with a process that resolves the currency from another data source.

### 6.2. Do Not Infer Defaults Out of Convenience

Some fallbacks can turn missing data errors into severe bugs:

```text
Missing currency -> implicitly assume VND
Missing tenantId -> implicitly use default tenant
Missing authScope -> implicitly grant full permissions
Missing timezone -> implicitly interpret as server's local timezone
```

Only use a default when it is an **evidence-backed** part of the V1 contract. For data that cannot be safely interpreted, reject or quarantine it with metrics and reprocessing capability.

### 6.3. Check Actual Serializer Configuration

Across Jackson, JSON-B, Gson, or other serializers, differences may exist in:

- Unknown property policy.
- Null/default and primitive conversion.
- Unknown enum handling.
- Date/time format.
- Naming strategy.
- Polymorphic typing.
- Record/class constructors.
- Validation annotations.
- Java module reflection access.

Upgrading a framework/JDK sometimes changes transitive serializer versions. Check the **effective dependency version and ObjectMapper configuration**, not only JSON fixtures.

### 6.4. Avoid Wire Formats Directly Coupled to Java Class Names

An example to avoid for long-term use:

```json
{
  "@class": "com.example.orders.internal.OrderEntity",
  "id": 123
}
```

When refactoring packages, shading, upgrading frameworks, or modularizing, FQCNs can change. A good wire contract uses stable schema identifiers such as `eventType`, `schemaVersion`, or managed DTO types, rather than making consumers load arbitrary classes from payloads.

This also reduces security risks from uncontrolled polymorphic deserialization.

## 7. HTTP API Contracts When Old and New Serve Concurrently

### 7.1. Old Requests to New

NEW must accept the request formats that clients and other services are currently sending, unless the API endpoint/version is intentionally changed.

For example, OLD accepts:

```json
{"customerId":"C-7"}
```

NEW wants to add `locale`. During a mixed-version rollout, NEW must support requests omitting `locale` or expose a newly versioned endpoint.

### 7.2. New Responses to Old Clients

Even when OLD and NEW sit behind the same router, old clients can receive responses from NEW. If a client rejects unknown fields, shape changes, or new enum values, the canary can break the client.

Checklist table:

| Response Change | Risk |
| --- | --- |
| Add optional field | Usually safe if clients ignore unknown fields; must test. |
| Remove field | Old clients may crash or lose data. |
| Change field type | Deserialization failure or wrong logic. |
| Rename field | Equivalent to removing the old field for un-updated clients. |
| Add new enum/status | Old clients may not know how to handle it. |
| Change HTTP status/headers | Proxy/client retries, caching, and error handling may differ. |
| Change pagination/ordering | Clients may skip or duplicate items. |
| Change auth/session cookie | Clients or old instances may fail authentication. |

### 7.3. A Versioned API May Suit Better Than a Compatibility Shim

If a large change cannot maintain compatibility, both can be served concurrently:

```text
/api/v1/orders    -- old contract
/api/v2/orders    -- new contract
```

Or select the protocol/schema version in the media type/header per your system's standards. What matters is **whether clients know how to select the version and whether the router/server upholds the contract**.

Do not treat adding `/v2` as an automatic solution for shared databases/messages: the backend still needs an appropriate data contract.

### 7.4. Authentication and Sessions

In a rolling deployment, a user may log in through OLD and then send the next request to NEW. Check:

- JWT claims understood by both versions.
- Session token/cookie format and encryption keys.
- Shared session store serializer.
- CSRF tokens and state.
- API gateway header behavior.
- Redirect/URL/cookie SameSite/Domain attributes.
- Key rotation and token lifetimes.

If NEW issues tokens that OLD cannot verify, a rollback or a request routed to OLD can log users out en masse.

## 8. Message Brokers and Event Schemas When Producers/Consumers Differ in Version

### 8.1. Producers and Consumers Are Not Upgraded Simultaneously

In systems using Kafka, RabbitMQ, or another message bus:

```text
OLD Producer ----\
                  >---- Topic / Queue ----> OLD Consumer
NEW Producer ----/                  \
                                     ---> NEW Consumer
```

There can be **messages published before the deployment**, messages from NEW producers during canary, and messages retried after rollback.

Therefore, consumers must know how to process payloads that may exist within the retention window, not only payloads from the newly deployed version.

### 8.2. Stable Event Envelope

An illustrative event envelope:

```json
{
  "eventId": "e-8f21",
  "eventType": "OrderPaid",
  "schemaVersion": 1,
  "occurredAt": "2026-10-15T09:30:00Z",
  "orderId": "O-123",
  "amountMinor": 120000,
  "currency": "VND"
}
```

Fields such as `eventId` and `schemaVersion` help with idempotency and version handling, but **merely adding schemaVersion without implementing version-handling logic is not enough**.

You must specify:

- Unique Event ID stable across retries.
- Event type/version.
- Field semantics, null/default behavior.
- Key/partition and ordering within broker guarantees.
- Retention/replay and compatibility duration.
- Handling of unknown schemas/fields.
- Dead-letter/quarantine when safe processing is impossible.

### 8.3. Additive Schemas Are Not Always Sufficient

With JSON, ignoring unknown fields depends on the decoder. With Avro or Protobuf, schema evolution has specific rules regarding field types, tags/field numbers, default values, and reader/writer compatibility.

Do not apply a blanket rule "adding a field is safe" across all formats.

For example, with Protobuf, **never reuse deleted field numbers**; use `reserved` when removing fields to prevent old messages from being misinterpreted if a field number is reused with a new meaning. With Avro, verify schema resolution rules and appropriate reader/writer defaults.

If using a Schema Registry, choose the compatibility policy matching your rollout pattern: backward, forward, full, and transitive modes serve different purposes depending on the system. A policy allowing new producers/consumers to work together does not necessarily allow rolling back to an old consumer.

### 8.4. Defer Emitting New Event Types

A safe strategy:

1. Deploy consumers capable of **reading** the new event type/field without using it yet.
2. Verify that OLD and NEW consumers run smoothly side by side.
3. Deploy producers capable of emitting the new event while keeping the feature flag off.
4. Wait until all critical consumers have been upgraded.
5. Enable emission of the new event.
6. Monitor errors and remove fallback logic only after the retention/rollback window expires.

This is the **reader before writer** order for schema changes that cannot be safely handled by old consumers.

### 8.5. Do Not Confuse "Old Consumers" with "Old Messages"

A new consumer must be able to read messages produced hours or days earlier, depending on retention. Conversely, if rolling back to an OLD consumer, it may receive new messages emitted by a NEW producer.

Therefore, tests must cover both:

- OLD payload fixtures → NEW decoder.
- NEW payload fixtures → OLD decoder.
- Replay with event ordering/retries.
- Unknown fields and enum values.
- Batches containing interleaved V1/V2 messages.

## 9. Database: Expand–Migrate–Contract

### 9.1. The Problem When OLD and NEW Share a Database

This situation easily makes rollback dangerous:

```text
          OLD instances -----+
                             |
                             v
                          Database
                             ^
                             |
          NEW instances -----+
```

If NEW immediately renames or drops a column that OLD still accesses, OLD may hit SQL errors. If NEW adds a `NOT NULL` constraint while OLD does not write that field yet, OLD may fail to insert/update.

Database changes must be rolled out in an order that **does not break still-live writers/readers**.

### 9.2. Expand: Additive Schema Changes

Suppose the initial table is:

```sql
CREATE TABLE orders (
    id VARCHAR(64) PRIMARY KEY,
    customer_name VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL
);
```

NEW wants to use the standard name `customer_display_name`. Instead of renaming the column immediately:

```sql
ALTER TABLE orders
    ADD COLUMN customer_display_name VARCHAR(255);
```

During the expand phase:

- OLD continues reading/writing `customer_name`.
- NEW must be able to read records lacking the new field.
- Do not immediately enforce `customer_display_name NOT NULL` while OLD writers have not been updated.
- New indexes/constraints must be evaluated for locks, workload impact, and long-running migrations.

The SQL illustrates relational system logic; exact migration syntax and locking behavior depend on the specific database/version.

### 9.3. Migrate: Controlled Backfill

Example:

```sql
UPDATE orders
SET customer_display_name = customer_name
WHERE customer_display_name IS NULL;
```

This command illustrates backfill logic, **not a recommendation to run a giant single transaction in production**. For large tables, batching, checkpointing, rate limiting, monitoring, and assessing locks/replication lag for your actual database are required.

More importantly, **OLD writers may still continue updating `customer_name`**. If NEW prioritizes reading `customer_display_name` while that column is not updated in sync, NEW may read stale values.

Several options exist:

- Keep `customer_name` as the authoritative data source during the mixed-version phase; NEW reads it preferentially and writes both when appropriate.
- Use migrations/triggers or an application compatibility layer with verified synchronization rules to keep both columns consistent, if the database and system permit.
- Defer switching the authoritative source until all OLD writers have exited the system.
- Use versioning or timestamps to detect conflicts if the data model requires it.

Do not apply **naive dual-write** and assume both copies of the data will always stay identical.

### 9.4. Contract: Drop the Old Column Last

Only after:

1. No OLD binary/OLD writer remains using the old column.
2. No old batch jobs, workers, reports, scripts, or operational tools remain.
3. NEW has stably used the new data source.
4. Backfill is complete and reconciled.
5. The rollback window to OLD has closed or another rollback path exists.
6. Backup/restore and migration plans are approved.

...should you consider dropping the old column:

```sql
ALTER TABLE orders DROP COLUMN customer_name;
```

This is a **contract** change that may not be easily reversible. Do not perform it in the same release as adding the column if rolling back to the old application remains possible.

### 9.5. Sample Flow

```text
Release A (OLD running)
  |
  v
DB expand: add nullable column, keep old column
  |
  v
Release B: NEW has dual-read; writer still preserves old contract
  |
  v
Backfill + monitor divergence and concurrent writes
  |
  v
Rolling/canary NEW; OLD and NEW running concurrently
  |
  v
All OLD readers/writers exit the system
  |
  v
Switch authoritative source per policy and verify
  |
  v
Rollback/retention window ends
  |
  v
DB contract: drop old column/API in a later release
```

The exact sequence must be tailored to your schema, actual data, and migration tool. The invariant rule is **never remove a boundary that OLD relies on while OLD can still run**.

## 10. Dual-Write: Distinguishing Different Patterns

### 10.1. Dual-Writing Two Columns in One Transaction

NEW writing both the old and new columns within the same database transaction ensures they commit together, yet OLD writers still know only the old column. Therefore, updating only NEW is insufficient.

In mixed-version operation, you must define:

- Who is permitted to write data?
- Which field is authoritative?
- Can OLD write after NEW?
- What happens with bidirectional updates?
- Can updates be lost when backfill runs concurrently?
- By what rule do readers choose a field?

### 10.2. Dual-Writing to Two Independent Systems

For example, the application writes simultaneously to a database and Kafka:

```text
Application
   ├── write Database
   └── publish Event
```

If the database commit succeeds but publishing fails, the two systems become inconsistent. If publishing occurs first and the database rolls back, consumers may observe an event that does not match real state.

This is an **atomicity across two systems** problem and cannot be solved merely by calling two APIs sequentially and retrying unconditionally.

A common solution is the **transactional outbox**:

```text
In a single DB transaction:
  - Update order
  - Insert outbox event
             |
             v
Commit
             |
             v
Outbox dispatcher/CDC publishes to broker
             |
             v
Consumer processes idempotently by eventId
```

An outbox still requires retries, duplicate event handling, and monitoring; it does not automatically guarantee end-to-end exactly-once semantics for every side effect.

### 10.3. Dual-Read Does Not Mean Dual-Write

You may need NEW to read both old and new fields while **still prohibiting writing the new format** during the rollback window. This is typically a safer rollout state.

Separate feature flags or release steps:

- Can read V1?
- Can read V2?
- Can write V2?
- Can remove V1?

The "reader first, writer later" approach reduces the risk of NEW emitting a format that OLD cannot accept.

## 11. Shared Cache, Distributed Sessions, and Serialized Objects

### 11.1. Cache Format Is a Data Contract

OLD and NEW may share Redis, Memcached, or a distributed cache. An entry written by NEW may later be read by OLD.

For example, OLD stores:

```json
{"id":"U-7","roles":["USER"]}
```

NEW adds:

```json
{"id":"U-7","roles":["USER"],"permissions":["orders:read"]}
```

If OLD does not understand `permissions`, it may fail or ignore it. More dangerously, NEW reading an old cache entry might **implicitly grant default permissions** when the new field is missing. Cache contracts must handle both directions properly and pay close attention to security semantics.

### 11.2. Avoid Java Native Serialization as a Cross-Version Contract Whenever Possible

`ObjectOutputStream` embeds class names, `serialVersionUID`, and object structure. When upgrading classes, refactoring packages, changing JDK/frameworks, or changing class loaders, an older serialized object may fail to deserialize.

For caches/sessions shared across multiple versions, prefer a format governed by a stable schema (JSON/Protobuf/Avro with explicit policy) or use versioned cache namespaces with a transition plan.

Do not assume keeping the same `serialVersionUID` guarantees compatibility across all class changes.

### 11.3. Versioned Cache Keys

You can use:

```text
user-profile:v1:<id>
user-profile:v2:<id>
```

This isolates formats, at a cost:

- Both versions can become stale differently.
- Cache invalidation must handle both v1 and v2.
- Hit rates and memory usage can change.
- Rollback requires the v1 cache or rebuild capability.
- Do not treat v2 as an authoritative data source invisible to v1.

Versioned keys are one option, not a substitute for data consistency design.

### 11.4. Session Stickiness Only Partially Solves the Problem

Pinning a session to one version can reduce direct client errors, but does not address:

- Background jobs sharing the same database.
- Event consumers running different versions.
- Shared Redis/session stores.
- Failover to another instance.
- Mid-session rollback.
- Queues holding messages emitted by the new version.

Therefore, sticky routing is not proof of a safe shared data contract.

## 12. How Do Java and Framework Migrations Alter Contracts?

### 12.1. The JDK Does Not Directly Change Wire Schemas, but Affects Implementations

Upgrading the JDK can introduce differences in:

- Default charset of several Java APIs.
- Date/time, timezone database, or locale data.
- TLS/security providers.
- Java serialization/class loading.
- Reflection/module access.
- Libraries/drivers upgraded to support the new JVM.

A message with identical JSON can still cause behavioral incompatibility if timestamps parse differently, timezones differ, or encodings are misinterpreted.

### 12.2. UTF-8 and Vietnamese Text Data

Since Java 18, JEP 400 standardizes the default charset as UTF-8 across many applicable Java SE APIs. If OLD previously wrote text files using another platform charset while NEW reads them as UTF-8, data can become corrupted.

In mixed-version environments, file/export data is part of the contract: switch to UTF-8 only when relevant producers/consumers agree on source/target encodings, backed by byte-level fixture tests and a process for handling legacy data.

For HTTP/JSON wire protocols, follow the protocol standard and consumer contract encoding; do not assume every party automatically handles things properly just because the JVM defaults to UTF-8.

### 12.3. Jackson, JSON-B, and Serializer Upgrades

When upgrading Spring Boot, Jakarta EE, or JSON libraries, defaults may differ for date/time, enums, unknown fields, and null handling. Consequently, the same DTO source can produce different JSON bytes.

Use **golden fixtures** to verify contracts at the byte/field/semantic level, and test old/new readers and writers. Do not compare only `toString()` on Java objects.

### 12.4. ORM and Jakarta Migration

Migrating from the `javax.persistence` generation to `jakarta.persistence` is an API/framework change, yet the shared database must still satisfy the schema contract. Two ORM versions can differ in:

- Type mapping and SQL dialect.
- Default schema generation behavior.
- Identifier generation.
- Enum mapping.
- Timestamp/numeric precision.
- Lazy loading and transaction semantics.

If OLD and NEW ORMs read/write the same table concurrently, test with real data and critical SQL queries, and avoid accidentally enabling schema auto-update/drop mechanisms in production during a rolling deployment.

### 12.5. Module Path and Serialization Frameworks

JPMS may require `opens` for frameworks using deep reflection. NEW running on the module path may fail deserialization while OLD running on the classpath succeeds.

Verify runtime module access for serializers/ORMs. Do not add `--add-opens` across the entire JDK to silence every error; prefer compatible library versions and open only the specific packages needed.

## 13. Feature Flags and Rollout Order for New Capabilities

### 13.1. Separate "Deploy Code" from "Activate Behavior"

A NEW version can be deployed while still **writing the V1 format**. This allows observing the new code before emitting the new data format.

Example feature flags:

```text
read_schema_v2 = true
write_schema_v2 = false
emit_new_status = false
use_new_database_column = false
```

Only after enough readers support the new format should `write_schema_v2` be enabled per plan.

Flags need an owner, clear defaults, per-environment state, and a removal schedule so temporary compatibility branches do not persist indefinitely.

### 13.2. Reader Before Writer

A sequence suitable for many additive changes:

1. Deploy NEW readers able to read V1/V2 while still writing V1.
2. Verify mixed readers work together.
3. Upgrade dependent consumers.
4. Enable the V2 writer in a small scope once OLD readers are safe or have exited the system.
5. Monitor errors and keep rollback scoped.
6. Remove V1 after the retention/rollback window.

Do not apply this mechanically if a contract requires simultaneous changes for safety. Still, it is **an important ordering principle** that prevents new data from being misread by old consumers.

### 13.3. Flags Must Be Consistent Across Multiple Instances

If NEW instance A enables the V2 writer while NEW instance B has not, the shared DB/messages can contain both formats. Readers must be prepared for this, or flags must be coordinated centrally according to plan.

Do not assume changing config on one pod updates every pod simultaneously. Record the timestamp/version of flag activation to correlate with data errors.

## 14. Traffic Routing, Canary, and Shadow Traffic

### 14.1. Canary Measures More Than HTTP 200

Metrics to monitor separately for OLD and NEW:

- 4xx/5xx and business errors.
- p50/p95/p99 latency.
- Deserialization/validation failures.
- Database errors and schema constraint violations.
- Event processing lag, DLQ, and retry counts.
- Duplicate side effects and idempotency conflicts.
- Cache/session failures.
- CPU, heap, GC, and connection-pool saturation.
- Security metrics: auth failures, permission mismatches.
- Version distribution by request/job/consumer.

A 5% canary with a clean HTTP success rate that continually emits messages unreadable by OLD consumers must still be blocked.

### 14.2. Shadow Traffic Carries Side-Effect Risks

*Shadow traffic* duplicates real requests to NEW to observe behavior without returning NEW's response to the client:

```text
Client ---> OLD (primary response)
             \
              \-- copy --> NEW (shadow, response not returned to client)
```

If shadow NEW executes **database writes, payment charges, event publishing, or email sending**, requests can cause duplicate side effects. **Never unconditionally mirror real write requests.**

Handling depends on the use case:

- Shadow only suitable read-only endpoints.
- Use isolated sandboxes/datasets.
- Disable side effects through verified mechanisms.
- Replace external gateways with stubs in test environments.
- If comparing write behavior is needed, use controlled replay on isolated data.

Even GET requests can trigger indirect side effects such as updating last-access timestamps, rate limits, or cache writes. Verify actual behavior.

### 14.3. Attach Version Metadata for Observability

You can include application versions in structured logs/traces/metrics, for example:

```text
app.version=old-1.8.4
app.version=new-2.0.0
schema.read=v1
schema.write=v1
```

For events, include the version in the envelope if the contract permits. For databases, use appropriate auditing/versioning to trace record origin during incidents.

Avoid logging sensitive personal data just to debug compatibility.

### 14.4. Health, Readiness, and Draining

During a rolling deployment:

- NEW receives traffic only after passing critical readiness checks.
- OLD stops accepting new requests before shutting down.
- In-flight requests and background jobs must have drain/cancellation policies.
- Consumer group rebalancing and message acknowledgments are handled properly.
- Schedulers must not create duplicate jobs when both OLD and NEW are active.

An HTTP service receiving zero traffic does not guarantee **all background workers** of the old version have stopped.

## 15. Background Tasks, Schedulers, and Idempotency

### 15.1. When Both Old and New Run Scheduled Jobs

If both versions contain the scheduled job:

```text
OLD job scheduler ----> issue invoices 00:00
NEW job scheduler ----> issue invoices 00:00
```

Both jobs may run together and issue invoices twice. That is a **coordination** bug, not merely a schema bug.

You need one of the appropriate mechanisms:

- Leader election.
- Distributed lock/lease with timeout and fencing if needed.
- A centralized scheduler.
- Explicit job assignment/cutover.
- Idempotency keys or unique constraints where side effects are written.
- Separated deployment roles: HTTP workers, consumers, schedulers.

A distributed lock alone does not always guarantee exactly-once side effects, especially if a lease expires while an old worker still executes the operation. Check fencing/transactions/idempotency for your problem.

### 15.2. Event Replay and Duplicate Processing

In mixed-version environments, consumers may rebalance or retry a message. If OLD and NEW code have different processing logic, ensure the final outcome remains correct.

Example deduplication table:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

A consumer can use unique keys and appropriate transactions to manage duplicate processing. However, design the **`consumer_name` and side-effect scope** carefully: if OLD and NEW use two different consumer names while performing the same business operation, two separate dedup records will not prevent duplicate business effects.

### 15.3. Idempotency Keys Must Have the Same Semantics

If OLD uses the request ID as the idempotency key while NEW uses the order ID, both versions may treat the same operation as two distinct operations.

When sharing data, standardize key format, TTL, business meaning, and race behavior. Especially for payments or inventory, protect invariants at the storage/transaction layer where appropriate.

## 16. Contract Testing Using a Version Matrix

### 16.1. Producer–Consumer Matrix

For APIs, messages, caches, and file formats, you can organize:

| Case | Input/Producer | Consumer/Reader | Expected Outcome |
| --- | --- | --- | --- |
| T1 | V1 JSON | OLD | Baseline pass. |
| T2 | V1 JSON | NEW | NEW understands historical data. |
| T3 | V2 JSON | NEW | Target functionality passes. |
| T4 | V2 JSON | OLD | Pass or **V2 emission is blocked** while OLD still runs. |
| T5 | V1 missing optional field | NEW | Verified default, no fabricated data. |
| T6 | V2 with unknown enum | OLD/NEW | Safe handling per contract or quarantine. |
| T7 | Mixed V1/V2 with retry/replay | OLD/NEW | No duplicate side effects, no lost events. |
| T8 | V2 written, roll back to OLD | OLD | Rollback path confirmed. |

A T4 case that cannot pass semantically is proof that the **V2 writer is not yet allowed to be enabled**, not a reason to skip the test.

### 16.2. Contract Fixtures Should Include Edge Cases

Do not test only complete payloads:

- Missing required fields.
- Missing, null, or empty optional fields.
- Unknown fields.
- Unknown enums/statuses.
- Large numbers, decimal precision, and overflow.
- Vietnamese Unicode and special characters.
- Timestamps with differing offsets, timezones, and precision.
- Empty nested objects/arrays.
- Duplicate/out-of-order events.
- Payloads **actually** produced by the OLD serializer, not only hand-written JSON.
- Historical data already existing in storage.

### 16.3. Consumer-Driven Contract Tests

If multiple services consume an API, consumers can specify the fields/statuses they rely on. The candidate producer is verified against these contracts before deployment.

Manage contract versions according to actually deployed consumers. A contract test run only against the latest consumer source in the repository can miss an older consumer version still running in production.

### 16.4. Testing with a Schema Registry

If using Avro/Protobuf/JSON Schema in a registry:

- Check the compatibility policy matching your rollout plan.
- Register candidate schemas using the registry's validation mechanism.
- Test decoding V1/V2 writer fixtures with the corresponding readers.
- Check field numbers, defaults, and migration aliases where supported by the format.
- Test across the retention/replay window, not just the latest schema.

A registry policy is a valuable quality gate, yet it **does not prove semantic compatibility** for enums, currencies, or business rules.

## 17. Integration Testing When Two Binaries Run Concurrently

### 17.1. Do Not Run Integration Tests Only on NEW

A staging environment can run concurrently:

```text
API Router
  |
  +---- OLD app instance
  |
  +---- NEW app instance
             |
             v
       Shared test database
             |
             v
       Shared test broker/cache
```

Use representative test data; never connect to the production database to test migrations.

Test cases:

1. OLD creates record → NEW reads/updates → OLD reads again.
2. NEW creates record → OLD reads/updates → NEW reads again.
3. OLD emits event → NEW consumer processes.
4. NEW emits event → OLD consumer processes or emission is blocked per rule.
5. Both versions update the same record → invariants hold.
6. NEW runs partially then rolls back to OLD → data remains valid.
7. Session created by OLD is served by NEW if topology allows.
8. Consumer rebalance/restart neither drops nor duplicates business effects.

### 17.2. Test Coexisting Writers

A system can pass the "OLD can read NEW" test yet fail when **both versions update concurrently**. For instance, NEW writes a new field, and OLD performs a full-entity update that accidentally clears or overwrites the unknown field.

Tests should verify:

- Partial updates vs. full-object replacement.
- ORM dirty checking and optimistic locking.
- `version` column or compare-and-swap policies.
- Lost updates between backfill and live writes.
- Null overwrites on fields known only to NEW.
- Migrations running concurrently with user traffic.

This is a data consistency problem, not merely schema parsing.

### 17.3. Test Concurrent Schema Migrations

Migration tools like Flyway or Liquibase are often used to manage schema versions. When multiple pods start up simultaneously, an appropriate locking/execution mechanism is required; do not let every pod run destructive migrations independently.

Distinguish **schema migration rollout** from **application rollout** in the release plan, especially for backward-incompatible changes.

### 17.4. Minimum Deployment Matrix

| State | OLD | NEW | Schema/Data | Testing |
| --- | --- | --- | --- | --- |
| Baseline | 100% | 0% | V1 | OLD regression. |
| Expand ready | 100% | 0% | Expanded, still V1 writes | OLD still works. |
| Mixed | 80% | 20% | Shared contract | Cross-version + canary. |
| Near-complete | 10% | 90% | Shared contract | Background workers, retries. |
| New steady | 0% | 100% | Still rollback-safe | Full regression/observability. |
| Contract cleanup | 0% | 100% | Schema V2 only | Only after the rollback window ends. |

Percentages are illustrative. A real pipeline may choose steps like 1% → 5% → 25% → 100% based on traffic and risk level.

## 18. Defining the Rollback Window and the "Point of No Return"

### 18.1. Code Rollback Differs from Data Rollback

Quickly reverting to the OLD container does not mean OLD can read the data NEW just wrote.

Some changes are difficult to reverse:

- Dropping/renaming a column used by OLD.
- Changing payload formats without a backward reader.
- Emitting enums/statuses unknown to OLD.
- Changing hashing/encryption/session serialization mechanisms.
- Shifting currency units/timezones so data no longer shares semantics.
- Moving data to another store and decommissioning the old source.
- Triggering external side effects (payments, emails, events) without undo.

Distinguish:

- **Reversible rollout:** reverting to OLD leaves data/config valid.
- **Forward-only migration:** after a specific contract/activation step, you must move forward with a new fix rather than simply redeploying OLD.

### 18.2. Defining the Compatibility Horizon

An organization may commit to supporting at most two application versions concurrently, e.g., `N` and `N−1`, for a defined period.

However, with 14-day message retention and weekly batch jobs, data created by V1 can outlive a few-minute rolling deployment. The compatibility horizon must cover:

- Duration of old/new coexistence.
- Rollback window.
- Message retention/replay.
- Cache TTL/session lifetime.
- Long-lived database records.
- Batch/import/export schedules.
- Mobile/desktop clients that do not update simultaneously.

Do not decide to remove a compatibility shim just because the OLD pod count has been 0 for a few minutes.

### 18.3. Set Conditions to Close the Rollback Window

Before switching the schema to V2 only:

- No OLD pods/processes/consumers/jobs remain.
- No external consumers still require V1/V2 under policy.
- No V1 messages remain to process, or NEW continues reading V1 long-term.
- Data backfill is complete and no V1 writers remain.
- No V1 session/cache entries remain that cause errors, or a reader path exists.
- The new version has remained stable against SLOs for the defined period.
- Appropriate change management approval has been granted.
- Backups, runbooks, and recovery plans exist for severe incidents.

## 19. Tracing Incidents When Mixed-Version Runs Incorrectly

| Symptom | Possible Cause | Investigation Steps |
| --- | --- | --- |
| Some requests fail randomly depending on pod | OLD does not understand new response/request format or new state. | Tag `app.version` in logs; compare payloads per instance. |
| After rollback, OLD fails to start | Database dropped/renamed old column; incompatible migration version. | Inspect schema history and contract changes. |
| OLD consumer DLQ spikes after canary | NEW producer emitted enum/field/event type unsupported by OLD. | Inspect event fixtures, `schemaVersion`, and reader errors. |
| NEW misreads old data | Missing valid default, wrong charset/timezone/ORM type mapping. | Compare raw stored data, serializer, and historical contract. |
| NEW sees stale new field | OLD writer still writes only old column; inconsistent backfill/dual-write. | Trace writers, authoritative field, and transaction timeline. |
| Duplicate orders/charges | OLD+NEW schedulers or consumers ran concurrently without idempotency. | Check Event IDs, locks, uniqueness, and side-effect logs. |
| Cache deserialization fails | New cache entry has different class/format from old version. | Inspect cache schema/versioned keys/TTL. |
| Users logged out when switching pods | Different session format/encryption or cookie policy. | Check session store and token compatibility. |
| Latency rises without HTTP errors | Queues, DB pool, backfill, indexes, or dual-write overhead. | Check p99, DB locks, connection metrics, and queue lag. |
| Shadow requests send real emails/payments | Shadow path did not isolate side effects. | Audit sinks and stop shadow write traffic. |
| OLD–NEW tests pass yet production fails | Profile, schema, dependency, or data volume differs from staging. | Compare artifact checksums, effective config, and sampled real data. |

Diagnostic rule: record **writer version, reader version, schema version, and data path**. Having only a stack trace without knowing which version generated the payload makes root-cause analysis much slower.

## 20. Phased Mixed-Version Release Process

### Phase 0: Lock Baseline and Contract

1. Snapshot OLD version, JDK, framework/BOM, schemas, serializer configs, and DB/queue/cache.
2. List all producers/consumers of shared data.
3. Define the compatibility matrix and rollback window.
4. Save real payload fixtures, test reports, and business invariants.
5. Assign owners for schema/API/event/database migrations.

### Phase 1: Prepare Readers and Database Expand

1. Add schema changes strictly in ways that do not break OLD.
2. Upgrade NEW readers to understand V1/V2.
3. Keep writers on the V1 contract if OLD is not yet safe with V2.
4. Deploy any required compatibility layers.
5. Run contract tests and mixed-version integration tests.

### Phase 2: Release New Code Canary

1. Enable NEW at a small percentage.
2. Enable only traffic and features proven not to break OLD.
3. Monitor decode errors, data divergence, side effects, SLOs, and DB load.
4. Have a rehearsed kill switch/rollback procedure.
5. Halt expansion if shared data is corrupted, even if HTTP success rate looks fine.

### Phase 3: Migrate Writers/Consumers by Dependency

1. Upgrade remaining consumers still dependent on the old format.
2. Enable the new writer via flag once old readers are protected or gone.
3. Backfill data in checkpointed batches.
4. Reconcile old/new fields and resolve discrepancies.
5. Monitor queue replay, session caches, and background jobs.

### Phase 4: Reach NEW Steady State

1. Confirm all critical applications/workers are on NEW.
2. Retain the ability to read V1 as long as old data may exist.
3. Measure SLOs and validate data after canary/full traffic.
4. Lock in rollback closure timing if irreversible contract changes apply.

### Phase 5: Contract Cleanup in a Separate Release

1. Confirm no OLD writers/readers remain within the committed scope.
2. Remove old fields/columns/endpoints/cache formats when conditions are met.
3. Remove temporary feature flags and adapters.
4. Re-run tests against historical data and the new schema.
5. Update contract documentation, runbooks, schema registry, and migration logs.

## 21. Contract Template and Deployment Checklist

### 21.1. Sample Contract Worksheet

```text
Data contract:
  Name:
  Owner:
  Producers (version + deployment):
  Consumers (version + deployment):
  Storage/transport:
  Wire format / schema ID:
  Charset / timestamp / numeric semantics:
  Required / optional / nullable fields:
  Unknown field and enum policy:
  Compatibility promise:
  Minimum reader versions:
  Earliest allowed new writer:
  Retention/rollback window:
  Idempotency/ordering rules:
  Failure handling / DLQ:
  Verification fixtures:
  Schema/backfill/cleanup plan:
  Rollback plan:
```

### 21.2. Checklist Before Running Concurrently

- [ ] Identified OLD/NEW versions and concurrent deployment topology.
- [ ] Identified all shared data: APIs, DB, events, caches, sessions, files.
- [ ] Established explicit data contract for schemas, nulls/defaults, enums, and semantics.
- [ ] Tested OLD writer → NEW reader with real data.
- [ ] Tested NEW writer → OLD reader or blocked NEW emission while OLD is unready.
- [ ] Defined compatibility horizon: rollout, rollback, retention, batch, and external clients.
- [ ] Checked JSON/ORM/JDK changes affecting serialization, charset, and timezone.
- [ ] Designed DB expand before deploying app code requiring new fields.
- [ ] Protected OLD readers/writers throughout the migration.
- [ ] Defined authoritative data rules during dual-read/dual-write and a backfill plan.
- [ ] Tested concurrent writes, optimistic locking, and idempotency.
- [ ] Tested message replay/retries, unknown events, and DLQ handling.
- [ ] Addressed sessions, cache keys, tokens, and distributed schedulers.
- [ ] Verified shadow traffic does not duplicate real side effects.
- [ ] Added version tags to logs/metrics/traces and defined canary thresholds.
- [ ] Rehearsed rollback after NEW has written data.
- [ ] Defined the forward-only point if the rollout contains irreversible changes.
- [ ] Deferred destructive schema changes to a separate contract cleanup release.
- [ ] Updated runbooks, owners, schema registry, and criteria to close the rollback window.

## 22. Walkthrough: Safely Migrating the Order API from V1 to V2

### 22.1. Context

A Java 11 service currently runs V1 and wants to migrate to Java 21 and a new framework. V2 adds:

- Field `currency`.
- Field `amountMinor` gradually replacing `amount`.
- New status `ON_HOLD`.
- New database column `customer_display_name`.
- Event payload with `schemaVersion=2`.

The system uses rolling deployment with OLD and NEW sharing the DB, broker, and Redis. The rollback window is 24 hours, while messages may be replayed longer.

### 22.2. Change Classification

| Change | Immediately Safe for Mixed-Version? | Action |
| --- | --- | --- |
| Add optional `currency` | Only if OLD ignores unknown fields and defaults are valid | Test both directions; not required yet. |
| Replace `amount` with `amountMinor` | No if old field is removed | Add new field, keep old field, align units/authoritative source. |
| Emit `ON_HOLD` | No if OLD mishandles unknown enums | Keep emission off until old consumers are safe or retired. |
| Add nullable column | Usually a safe expand if DB migration is checked | Run migration before NEW; do not drop old column. |
| Event schema V2 | Only if readers and schema policy accept it | Reader before writer; fixture and replay tests. |
| JVM 21 / new framework | Does not directly change data contract, but may alter serialization behavior | Golden fixtures and mixed-version integration tests. |

### 22.3. Recommended Order

```text
(1) Capture V1 payload/db/event/cache baseline
       |
       v
(2) Expand schema: add optional columns/fields
       |
       v
(3) Deploy NEW code reading V1/V2, writing per V1 contract
       |
       v
(4) Mixed-version tests and canary
       |
       v
(5) Upgrade all readers needing to understand V2 fields/events
       |
       v
(6) Enable V2 writer via flag + verify idempotency
       |
       v
(7) Backfill, reconciliation, observe replay/rollback
       |
       v
(8) Confirm zero OLD + rollback window
       |
       v
(9) Contract cleanup in a later release
```

If the `ON_HOLD` status specifically is not understood by OLD, do not emit it in step 3. If replacing `amount` changes units or semantics, dedicated migration logic and contract tests are required before acceptance.

### 22.4. Success Criteria

Success is not merely `BUILD SUCCESS` or both applications returning HTTP 200. You must prove:

- V1 data remains readable on V2.
- Data V2 may emit during the mixed window does not break V1.
- No duplicate charges/invoices/event processing occur.
- Backfill and live writes do not cause stale data or lost updates.
- Session/cache/event replay continues working.
- Rollback to OLD after canary was rehearsed with real V2 data.
- Schema contracts are not dropped prematurely.
- SLOs/error rates meet defined thresholds.

## 23. Common Misconceptions

**"Having two versions behind a router means they can run concurrently."** False. A router does not protect shared DBs, brokers, caches, and background jobs.

**"NEW can read old data so rollback is safe."** False. Rollback requires OLD to handle newly written data or restricting the NEW writer.

**"Just adding one JSON field is always compatible."** False. The OLD deserializer might reject unknown fields or misinterpret semantics.

**"Two dual-written columns never diverge."** False. OLD writers may still update only the old column, and backfills can race with live updates.

**"Blue–green avoids schema migrations."** False if both environments share a database or message bus.

**"Shadow traffic cannot affect production."** False if the shadow path still executes side effects.

**"Pinning sessions to OLD/NEW is enough."** False. Shared data, failover, queues, and background workers remain separate boundaries.

**"Broker exactly-once means payments cannot be charged twice."** That does not follow. End-to-end side effects need proper idempotency and transactions/reconciliation.

**"Drop old fields as soon as 100% of pods are on NEW."** Not necessarily. Queue retention, batch jobs, external clients, and rollback windows may require keeping V1 longer.

**"Upgrading the JDK does not change the JSON API so no contract tests are needed."** False. Upgrading transitive serializers, ORMs, charset/timezone defaults, or frameworks can alter behavior even when DTOs look identical.

## 24. Conclusion

Running old and new versions concurrently is **a data compatibility and operational problem**, not merely a traffic-splitting technique. During the mixed-version window, OLD and NEW must agree on contracts in both read and write directions, preserve the business meaning of shared data, and maintain invariants under concurrent execution.

A reliable Java migration workflow requires **reader before writer**, **database expand–migrate–contract**, **feature flags separating deployment from activation**, **an OLD–NEW test matrix**, **idempotency**, **per-version observability**, and **rehearsed rollback on data created by NEW**. Old contracts should be removed only after no consumer/writer requires them and the rollback/retention window has been addressed. Thus, upgrading the JDK and frameworks can proceed incrementally without forcing full-system downtime or risking unrecoverable data corruption.

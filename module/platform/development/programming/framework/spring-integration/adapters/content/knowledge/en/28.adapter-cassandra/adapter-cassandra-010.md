# Designing idempotent Cassandra writes in Spring Integration

## 1. Problem: a single event can be delivered multiple times

Consider a payment-processing flow:

~~~text
JMS/Kafka/HTTP
   -> Inbound adapter / gateway
   -> Spring Integration MessageChannel
   -> Validate + Transformer
   -> Cassandra outbound channel adapter
   -> Apache Cassandra
   -> Acknowledge/commit source
~~~

An `OrderPaid(eventId=evt-10001)` event can reach the consumer multiple times due to flaky networks, client timeouts, broker redeliveries, Kafka replays, deployment restarts, or data reconciliation. **That is normal behavior in at-least-once architectures**, not necessarily a "buggy producer".

Suppose Cassandra persists the write successfully yet the response to the application is dropped. The application sees `DriverTimeoutException`, the JMS listener rolls back, and the broker redelivers the same event. If the consumer generates a new UUID every time, the Cassandra table ends up with **two rows for one business event**. If the consumer writes the same row yet sends two confirmation emails, the row looks fine while the **business effect still duplicated**.

The design goal is **idempotent processing**: upon receiving the same business event again, the system produces an outcome equivalent to the first valid execution, or recognizes the duplicate and handles it safely—even when the prior Cassandra request's result is unknown.

In the **SPRING_INTEGRATION_ADAPTERS** module, learners connect external systems to Spring Integration via inbound/outbound adapters, gateways, pollers, and `MessageChannel`, practicing file, SFTP, HTTP, JMS, AMQP, Kafka, and database sources alongside message contracts, errors, and connection lifecycles. This lesson in the **Adapter Cassandra** chapter focuses on designing safe re-execution across every path into Cassandra.

### Learning objectives

After this lesson, you will be able to:

1. Distinguish **CQL idempotence**, **business idempotency**, and **end-to-end effectively-once processing**.
2. Understand Cassandra `INSERT`/`UPDATE` **upsert semantics**, timestamp-based conflict resolution, TTLs, and **non-idempotent** operations like counter increments and list prepends.
3. Construct business event identities and Cassandra primary keys that remain **stable across retries, replays, backfills, and deployments**.
4. Detect **identical-content duplicates** vs **conflicting duplicates sharing an ID with different payloads**.
5. Compare unconditional upserts, `INSERT ... IF NOT EXISTS`/LWT, idempotency inboxes, and version-guarded state updates.
6. Design multi-table/multi-partition writes without assuming SQL-style atomic transactions or cross-system Cassandra–JMS/Kafka commits.
7. Implement Spring Data Cassandra, Java Driver, and Spring Integration Java DSL with explicit entity mapping, statement options, retries, and acknowledgment boundaries.
8. Test uncertain-outcome timeouts, source redeliveries, concurrent writers, TTL expiry, migrations, and reconciliation.

## 2. Three levels of idempotency to separate

| Level | Example | Intended guarantee | Does not guarantee by itself |
|---|---|---|---|
| **Statement-level** | `INSERT` with same full primary key and values | Re-execution adds no new business row | Does not guard against conflicting payloads or non-Cassandra side effects |
| **Event-level** | `OrderPaid(evt-10001)` received 10 times | The event is accepted only once as a valid event; duplicates are recognized | Does not atomically commit multiple tables together |
| **Workflow-level** | Write Cassandra + send email + commit JMS | After crashes/retries, workflow resumes without duplicate side effects | Does not form a single atomic transaction unless every system supports one |

**Idempotent** does not mean "executed literally once". A SQL/CQL operation can **be sent 5 times**, yet the table still holds **one row for that primary key**. That is **at-least-once execution with idempotent effects**, not exactly-once execution.

~~~mermaid
flowchart TD
    S["Broker delivers evt-10001"] --> F["Spring Integration flow"]
    F --> K["Derive stable event key"]
    K --> C["Cassandra write"]
    C --> A{"Cassandra ACK?"}
    A -->|"Yes"| B["Commit/ack broker per policy"]
    A -->|"Timeout / unknown"| R["Bounded retry / reconcile"]
    R --> F
    B -. "Broker commit fail/crash" .-> S
~~~

### 2.1. One database row does not mean one side effect

A consumer might perform:

~~~text
1. INSERT evt-10001 into Cassandra (idempotent upsert)
2. POST /charge to payment provider
3. Send confirmation email
4. Commit JMS/Kafka source
~~~

On replay, step 1 may target the same row while step 2 or 3 could run **a second time**. Therefore, enforce a **dedicated idempotency key at every external side-effect boundary**, or use an outbox/inbox with recoverable workflow state.

### 2.2. "Exactly once" must state its exact scope

Commonly confused terms:

- **At-most-once delivery:** messages may be lost, never actively redelivered.
- **At-least-once delivery:** duplicates may arrive, with redelivery when unconfirmed.
- **Exactly-once processing effect:** aims for a business outcome equivalent to once-only execution, typically achieved via idempotency, deduplication, and reconciliation.
- **Broker-level exactly-once transaction:** covers only resources/protocols managed by the broker framework, never automatically including Cassandra.

Never promise **end-to-end exactly-once** merely because Cassandra has LWTs, JMS has transacted sessions, or Kafka has transactional producers.

## 3. Cassandra INSERT is an upsert, not SQL's INSERT UNIQUE

A test table:

~~~sql
CREATE KEYSPACE IF NOT EXISTS shop_integration
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS shop_integration.events_by_id (
    tenant_id text,
    event_id text,
    order_id text,
    event_type text,
    payload_sha256 text,
    occurred_at timestamp,
    payload_json text,
    PRIMARY KEY ((tenant_id, event_id))
);
~~~

**Environment:** `dc1:3` applies only when a datacenter named `dc1` and at least three matching Cassandra replica nodes exist. In a single-node lab, create a keyspace with RF=1 and **do not** use it to claim proof of quorum or failover.

The table uses a **composite partition key `(tenant_id, event_id)`**. Each business event has a unique identifier **within its tenant scope**. This design serves lookups by event identity. If a timeline by order/month is also needed, add a dedicated table matching that query pattern rather than scanning the table with `ALLOW FILTERING`.

### 3.1. Unconditional INSERT twice

~~~sql
INSERT INTO shop_integration.events_by_id
    (tenant_id, event_id, order_id, event_type, payload_sha256,
     occurred_at, payload_json)
VALUES
    ('tenant-42', 'evt-10001', 'ORD-501', 'OrderPaid', 'hash-A',
     '2026-11-23T03:00:00Z', '{"eventId":"evt-10001"}');

-- Same full PK, same values:
INSERT INTO shop_integration.events_by_id
    (tenant_id, event_id, order_id, event_type, payload_sha256,
     occurred_at, payload_json)
VALUES
    ('tenant-42', 'evt-10001', 'ORD-501', 'OrderPaid', 'hash-A',
     '2026-11-23T03:00:00Z', '{"eventId":"evt-10001"}');
~~~

The result is **one logical row for that full primary key**. Yet because `INSERT` is an upsert, Cassandra **returns no "this was the first time" boolean** for unconditional inserts. If a subsequent write shares that key with `payload_sha256='hash-B'`, regular columns can be overwritten via **write-timestamp reconciliation**.

### 3.2. A primary key must capture complete identity

| Producer identity | Cassandra PK | Consequence |
|---|---|---|
| Globally unique `eventId` | `event_id` | Simple lookup, but uniqueness must truly be global |
| `eventId` unique only per tenant | `(tenant_id,event_id)` | Prevents cross-tenant collisions |
| `eventId` unique per order | `(tenant_id,order_id,event_id)` | Lookups must supply all key parts |
| Consumer mints new UUID per attempt | Different PK on replay | **Not idempotent** |
| Kafka offset as sole PK | Depends on topic/partition/replay path | Cannot serve as a universal business identity |

**Prefer a business `eventId` minted once by the producer when the event originates**, carried in the message and preserved across all retries. If a producer lacks a stable ID, define a **deterministic identity strategy** from immutable source fields and uniqueness rules—never use current processing time.

### 3.3. Conditionally safe upserts

Writing the same key and values can be treated as idempotent when:

1. The event body is canonicalized and immutable.
2. All primary-key components are deterministic.
3. No non-Cassandra side effects live inside the retried operation.
4. Mutation timestamp and TTL semantics introduce no unintended changes.
5. No concurrent writers hit the same key with differing payloads whose write order violates business invariants.

These are **conditions to verify**, not automatic properties of every `INSERT`.

## 4. Cassandra operations that are typically non-idempotent

| CQL/business action | Safe to repeat? | Reason |
|---|---|---|
| `SELECT` by key | Usually safe to resend | Results may vary under concurrent writes |
| `INSERT` with fixed PK, values, and timestamp policy | Usually row-safe | Must verify TTL and concurrency |
| `UPDATE SET state='PAID'` | Conditionally | Concurrent older writes can overwrite newer state |
| `UPDATE list_col = ['x'] + list_col` | **No** | Repeated prepends duplicate list elements |
| `UPDATE counter_col = counter_col + 1` | **No** | Retries increment counters again |
| `INSERT ... IF NOT EXISTS` | Conditionally | LWT returns `applied=false` if row exists; compare payloads |
| `DELETE` with same PK | Conditionally | Tombstones, timestamps, and concurrent writes matter |
| Multi-partition `BATCH` | Depends on **every mutation** | Logged batches do not create SQL transactions |
| Sending funds/email/HTTP callbacks | Not safe automatically | Needs downstream idempotency keys |

### 4.1. Counters and list appends are clear counterexamples

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.order_counters (
    order_id text PRIMARY KEY,
    processed_events counter
);

UPDATE shop_integration.order_counters
SET processed_events = processed_events + 1
WHERE order_id = 'ORD-501';
~~~

If the coordinator applies `+1` yet the response drops and the client retries, the counter can increment **twice**. Never mark this statement `setIdempotent(true)` solely for Java Driver retry convenience.

With CQL list appends/prepends, inserting the same element twice creates duplicate list entries; `set` has different semantics yet still requires evaluating concurrent updates and business deduplication.

### 4.2. UPSERT is not "first-write wins"

When two sources send:

~~~text
Source A: tenant-42 / evt-10001 / payload hash-A
Source B: tenant-42 / evt-10001 / payload hash-B
~~~

An unconditional upsert leaves whichever mutation carries the winning Cassandra **write timestamp** in the row, offering no guarantee the first payload survives. When **accept-once immutable events** are required, use a conditional insert/LWT or an idempotency claim protocol with conflict detection.

## 5. Creating stable event identities and partition keys

### 5.1. Keys are decided before publishing to the broker

Example event contract:

~~~json
{
  "tenantId": "tenant-42",
  "eventId": "evt-10001",
  "orderId": "ORD-501",
  "eventType": "OrderPaid",
  "schemaVersion": 1,
  "occurredAt": "2026-11-23T03:00:00.123Z",
  "amountMinor": 150000,
  "currency": "VND"
}
~~~

**`eventId` is created where the event originates**, never newly minted inside the Cassandra consumer. When a producer retries publishing, it reuses the **same `eventId`**. Source messages may carry a `JMSMessageID` or Kafka offset, yet those are transport coordinates—they do not automatically become business event IDs.

### 5.2. Rules for preserving identity across layers

| Layer | Must preserve | Avoid |
|---|---|---|
| Producer | Verified `tenantId`, `eventId`, `occurredAt`, event version | Minting a fresh ID on publish retry |
| JMS/Kafka message | Business ID + controlled immutable payload/headers | Relying solely on `JMSMessageID` or offset as event ID without a contract |
| Spring Integration `Transformer` | Canonical event fields and deterministic keys | Calling `UUID.randomUUID()` when the mapper re-runs |
| Cassandra entity | Full PK matching CQL schema | Shifting tenant/bucket/shard using consumer processing clock |
| Retry/reconciliation | Same event identity + payload fingerprint | Generating different values after a driver timeout |
| Backfill/migration | Mapping version + original event timestamp | Applying a new shard formula to legacy data without versioning |

### 5.3. Composite partition keys and time bucketing

Timeline table example:

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.events_by_order_month (
    tenant_id text,
    order_id text,
    bucket_month text,
    occurred_at timestamp,
    event_id text,
    event_type text,
    payload_sha256 text,
    PRIMARY KEY (
        (tenant_id, order_id, bucket_month),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
);
~~~

The partition key is **`(tenant_id, order_id, bucket_month)`**; clustering columns are **`occurred_at, event_id`**. If retries compute the bucket from current time, the same business event can land in a different partition.

~~~java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;

public final class StableEventKeys {
    private static final DateTimeFormatter MONTH =
            DateTimeFormatter.ofPattern("uuuu-MM");

    private StableEventKeys() {}

    public static Instant canonicalTime(Instant original) {
        if (original == null) {
            throw new IllegalArgumentException("occurredAt missing");
        }
        // Cassandra CQL timestamp stores millisecond precision.
        return original.truncatedTo(ChronoUnit.MILLIS);
    }

    public static String utcMonth(Instant occurredAt) {
        return MONTH.format(
                canonicalTime(occurredAt).atOffset(ZoneOffset.UTC));
    }
}
~~~

For `occurredAt=2026-11-30T23:59:59.999Z`, the bucket is always `2026-11` even if replayed on December 1 or next January. Standardize **UTC and canonical precision** across all services.

### 5.4. Stable sharding

If a table includes `shard` to prevent hot partitions, compute it via a **deterministic algorithm from event identity or a business discriminator**. Never use `ThreadLocalRandom` or a Kafka partition index that shifts when topics expand.

If migrating from 16 shards to 32 shards:

- `hash(eventId) mod 16` and `mod 32` yield different results for many legacy events.
- Existing data **does not migrate partitions automatically** when code deploys.
- You need a versioned shard scheme, dual-read/backfill, or a dedicated migration.
- Replay idempotency holds only when selecting the **same key version** as the original write.

## 6. Computing a payload fingerprint to detect conflicting duplicates

An idempotency key only tells you **two messages share an identity**. It does not verify **their contents match**. Two different payloads sharing the same `eventId` signal either a contract bug or an unintended overwrite.

### 6.1. Hashing raw JSON can cause false conflicts

These two JSON strings express identical data with different bytes:

~~~json
{"eventId":"evt-10001","amountMinor":150000}
~~~

~~~json
{ "amountMinor": 150000, "eventId": "evt-10001" }
~~~

Hashing **raw bytes** with SHA-256 produces different digests due to whitespace and field ordering. Therefore, to detect **semantic duplicates**, use a versioned **canonical payload format** rather than hashing raw JSON from arbitrary producer serializers.

### 6.2. Canonical DTO for storing fingerprints

~~~java
import java.time.Instant;

public record OrderPaidEvent(
        String tenantId,
        String eventId,
        String orderId,
        String eventType,
        int schemaVersion,
        Instant occurredAt,
        long amountMinor,
        String currency) {}
~~~

One way to avoid JSON ordering differences is updating the digest with fields **in fixed order with length prefixes**:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class EventFingerprint {

    private EventFingerprint() {}

    public static String sha256(OrderPaidEvent e) {
        if (e == null || e.tenantId() == null || e.eventId() == null
                || e.orderId() == null || e.eventType() == null
                || e.currency() == null || e.occurredAt() == null
                || e.amountMinor() <= 0 || e.schemaVersion() != 1) {
            throw new IllegalArgumentException("Invalid OrderPaidEvent");
        }

        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            update(digest, "OrderPaidEvent:fingerprint:v1");
            update(digest, e.tenantId());
            update(digest, e.eventId());
            update(digest, e.orderId());
            update(digest, e.eventType());
            update(digest, Integer.toString(e.schemaVersion()));
            update(digest, StableEventKeys.canonicalTime(
                    e.occurredAt()).toString());
            update(digest, Long.toString(e.amountMinor()));
            update(digest, e.currency());
            return HexFormat.of().formatHex(digest.digest());
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }

    private static void update(MessageDigest digest, String value) {
        byte[] data = value.getBytes(StandardCharsets.UTF_8);
        digest.update(ByteBuffer.allocate(4)
                .putInt(data.length).array());
        digest.update(data);
    }
}
~~~

This is **one versioned canonical encoding**, not a "universal standard" for all event types. Adding or altering fields requires **bumping the algorithm version** or maintaining explicit compatibility rules. Never omit business-critical fields (such as amount, currency, or `orderId`) from the fingerprint just to suppress conflicts. For Java `String`s, also standardize Unicode normalization if multiple producers/languages could encode characters differently.

### 6.3. Duplicate handling rules

| Scenario | `tenantId + eventId` | Fingerprint | Decision |
|---|---|---|---|
| New event | Absent | Any valid | Insert/claim allowed |
| Identical redelivery | Exists | **Equal** | Benign duplicate; skip repeated side effects |
| Producer reused ID for new payload | Exists | **Different** | Conflict; quarantine and alert |
| Same `eventId` in another tenant | **Different key** | Equal or different | Handle within tenant scope; never mix data |
| Retry changed hash algorithm | Same key | False mismatch possible | Maintain fingerprint version/compatibility |

**Hashes do not replace access control**: services must verify `tenantId` and message provenance before performing lookups or upserts. An `eventId` supplied by an HTTP client alone never authorizes which tenant can read or write.

## 7. TTLs, write timestamps, and last-write-wins: traps of "idempotent upserts"

### 7.1. TTL is measured from write time, so retries can extend lifetime

~~~sql
INSERT INTO shop_integration.events_by_id
    (tenant_id, event_id, order_id, event_type, payload_sha256)
VALUES
    ('tenant-42', 'evt-10001', 'ORD-501', 'OrderPaid', 'hash-A')
USING TTL 86400;
~~~

A 86,400-second TTL attaches to each written cell. Resending the identical statement an hour later **pushes back the expiration** of those rewritten cells because Cassandra computes TTL relative to the new write time. Hence "same key/same values" does not automatically equal **temporal idempotency**.

Do not confuse:

| Attribute | Meaning |
|---|---|
| Cassandra `USING TTL 86400` | Data lifetime after the write |
| Cassandra `USING TIMESTAMP n` | Write timestamp (microseconds) for conflict reconciliation |
| Java Driver `setTimeout(Duration)` | Client request deadline |
| JMS message time-to-live | Broker message retention |
| Business `occurredAt` | Event timestamp in the domain contract |
| Event retention deadline | Business policy governing event lifecycle |

**Sensible policies** depend on the domain: for an event ledger needing long-term deduplication, consider **no TTL** or a TTL exceeding every replay/backfill window. When a fixed business expiration timestamp is required, design and test remaining-TTL calculations, clock skew bounds, and write timestamps—never assume relative TTLs enforce absolute expiration times.

### 7.2. Newer write timestamps can overwrite older mutations

In Cassandra Java Driver 4.x, write timestamps come from `USING TIMESTAMP`, `Statement.setQueryTimestamp(...)`, the driver's timestamp generator (monotonic per session by default), or the server. Consequently, **two retries of identical CQL text do not share the same write timestamp**.

~~~text
Write A  t=1000: status=PAID
Write B  t=1200: status=CANCELLED
Replay A t=1300: status=PAID

Without a version guard, replaying A can regress
state from CANCELLED back to PAID.
~~~

Immutable append-by-ID event logs and current-state snapshots are **two different problems**:

- **Event log:** keep rows keyed by `eventId`; never overwrite an accepted payload.
- **Current state:** apply updates using `aggregateVersion`/compare-and-set or fenced ordering protocols, never implicit last-write-wins.

### 7.3. Should you set identical explicit timestamps across retries?

In regular CQL, timestamps can be set explicitly:

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement statement = SimpleStatement.builder(
        "INSERT INTO shop_integration.events_by_id "
        + "(tenant_id, event_id, order_id, event_type, payload_sha256) "
        + "VALUES (?, ?, ?, ?, ?)")
        .addPositionalValues(
                "tenant-42", "evt-10001", "ORD-501", "OrderPaid", "hash-A")
        .setQueryTimestamp(1_763_881_200_123_456L) // example microseconds
        .build();
~~~

The number above illustrates **microseconds since Unix epoch**, not millisecond business `occurredAt`. If repeatable event timestamps are needed, derive them from a **well-defined timestamp policy** persisted reliably. Even then, identical timestamps do not solve concurrent conflicting writes, deletes/tombstones, TTLs, or business conditions. For LWT conditional statements, **custom client write timestamps are disallowed** compared to regular statements.

**Note:** the driver's default timestamp generator is monotonic within a session; multiple application hosts/replicas lack a global clock guaranteeing business event order. Relying on LWW to enforce a state machine is rarely appropriate.

### 7.4. Null, UNSET, and partial updates

In Cassandra, sending `NULL` for a regular column usually means delete/tombstone, whereas `UNSET` in a driver bind skips touching that column. If retrying a `PATCH` message with an omitted field causes the mapper to emit an explicit null, it can wipe existing data.

Separate clearly:

1. Field **missing** in the event/patch.
2. Field **explicitly null** meaning delete.
3. Field **non-null** requiring an update.

Spring Data Cassandra's entity insert, update, and `WriteOptions` follow version-specific null rules. Never pass a DTO of nullable fields into `update(entity)` expecting the framework to guess "leave unchanged" in every case.

## 8. Choosing an idempotency strategy by business invariant

| Strategy | Best fit | Primary guarantee | Trade-off |
|---|---|---|---|
| **Deterministic upsert** | Immutable event logs where keys are never reused | Same PK spawns no extra rows | Upserts can overwrite conflicting payloads |
| **LWT `INSERT IF NOT EXISTS`** | First-write wins; must detect duplicates/conflicts | Conditional claim/insert in Cassandra | Consensus latency and lower throughput |
| **Optimistic version guard** | Current state updated sequentially by version | Blocks stale/out-of-order state regressions | CAS contention; must handle `applied=false` |
| **Durable inbox with state machine** | Multi-step workflows surviving crashes | Tracks `PENDING`/`COMPLETED`, claims, and replays | Requires recovery/fencing implementation |
| **Outbox in transactional source** | Reliable event emission from a source of truth | Ties publish to source transaction where supported | Does not atomically commit target Cassandra |
| **External idempotency key** | Payment/email/HTTP side effects | Downstream deduplicates repeated calls | Depends on downstream contract |
| **Reconciliation projection** | Writing multiple Cassandra tables | Repairs gaps when one write succeeds and another fails | Eventual consistency; requires monitoring/backfills |

### 8.1. First decision: true deduplication or safe upsert?

For immutable event histories:

- With a **single authoritative writer**, never-reused `eventId`s, and only needing the final row intact, **deterministic upsert** may suffice.
- With multiple producers capable of reusing `eventId`s, needing **the first payload immutable** and conflicting duplicates flagged, consider **LWT conditional inserts**.
- When an event triggers multiple side effects/steps, build **workflow state/inbox/reconciliation** rather than relying solely on a single-row LWT.

Do not slap `IF NOT EXISTS` onto every `INSERT` indiscriminately: Cassandra LWT adds consensus round-trips, latency, and contention—especially on hot keys.

## 9. Conditional INSERT with Cassandra LWT

`INSERT ... IF NOT EXISTS` guards writes so they succeed only when **the row does not exist yet**:

~~~sql
INSERT INTO shop_integration.events_by_id
    (tenant_id, event_id, order_id, event_type,
     payload_sha256, occurred_at, payload_json)
VALUES
    ('tenant-42', 'evt-10001', 'ORD-501', 'OrderPaid',
     'hash-A', '2026-11-23T03:00:00.123Z', '{"eventId":"evt-10001"}')
IF NOT EXISTS;
~~~

An LWT uses Cassandra's consensus protocol (Paxos and version-specific optimizations). It provides **compare-and-set within Cassandra's supported data scope**, not a multi-system SQL transaction.

### 9.1. Three outcomes to distinguish

| Outcome | Meaning | Action |
|---|---|---|
| `[applied]=true` | Conditional insert accepted | Continue workflow and ack per contract |
| `[applied]=false` | Row/condition already failed at check time | **Read existing row** and compare fingerprints |
| Timeout/Unavailable | Caller does not know whether it applied | Reconcile or retry carefully with the same key |

**Critical:** `applied=false` is not automatically a benign "must be a duplicate" success. Same event ID **with a different payload** must be flagged as **`CONFLICT`**, never silently ignored.

### 9.2. Java Driver 4.x example

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

public final class FirstWriteWinsDao {
    private final CqlSession session;
    private final PreparedStatement insertIfAbsent;

    public FirstWriteWinsDao(CqlSession session) {
        this.session = session;
        this.insertIfAbsent = session.prepare(
                "INSERT INTO shop_integration.events_by_id "
                + "(tenant_id, event_id, order_id, event_type, "
                + "payload_sha256, occurred_at, payload_json) "
                + "VALUES (?, ?, ?, ?, ?, ?, ?) IF NOT EXISTS");
    }

    public boolean tryInsert(EventRowData row) {
        BoundStatement statement = insertIfAbsent.boundStatementBuilder()
                .setString(0, row.tenantId())
                .setString(1, row.eventId())
                .setString(2, row.orderId())
                .setString(3, row.eventType())
                .setString(4, row.payloadSha256())
                .setInstant(5, row.occurredAt())
                .setString(6, row.payloadJson())
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .setSerialConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_SERIAL)
                .build();

        ResultSet result = session.execute(statement);
        return result.wasApplied();
    }
}

record EventRowData(
        String tenantId, String eventId, String orderId,
        String eventType, String payloadSha256,
        java.time.Instant occurredAt, String payloadJson) {}
~~~

This example targets a **test cluster with a matching local datacenter and replication topology**. `LOCAL_QUORUM` is regular consistency and `LOCAL_SERIAL` is LWT serial consistency; in multi-DC clusters, weigh cross-DC consistency and domain rules carefully. **Never set `setQueryTimestamp(...)` on LWTs**; Cassandra/drivers disallow arbitrary client timestamps on conditional statements.

### 9.3. When `applied=false`, compare against the existing row

~~~java
PreparedStatement read = session.prepare(
        "SELECT payload_sha256, event_type, order_id "
        + "FROM shop_integration.events_by_id "
        + "WHERE tenant_id = ? AND event_id = ?");

BoundStatement q = read.boundStatementBuilder()
        .setString(0, incoming.tenantId())
        .setString(1, incoming.eventId())
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .build();

var existing = session.execute(q).one();
if (existing == null) {
    // Do not assert "absent" when topology/consistency is unstable;
    // return an uncertain outcome or schedule reconciliation.
    throw new IllegalStateException("Cannot reconcile existing row");
}

boolean same = incoming.payloadSha256().equals(
        existing.getString("payload_sha256"));
if (!same) {
    throw new IllegalStateException("Conflicting event ID");
}
// Same fingerprint: valid duplicate, provided downstream effects
// have also completed or are safely replayable.
~~~

This is a **fragment** inside a DAO holding `session`, `incoming`, and compiled dependencies. Also verify schema/algorithm versions if the same ID can arrive across multiple message versions. **A duplicate in the event table does not prove downstream projections or side effects completed**; the inbox/recovery section below closes that gap.

### 9.4. When should LWT be used?

Choose LWT when:

- Concurrent writers can contend for the exact same event identity.
- A **first-write wins** policy must hold on a single row.
- State versions require compare-and-set.

Avoid LWT if your goal is pure throughput. Consensus makes it **costlier** than regular inserts and prone to bottlenecks on hot partitions. Enforce **the exact invariant needed** instead of sprinkling `IF NOT EXISTS` on every query.

## 10. Durable inbox: preventing duplicates and recovering incomplete work

An **idempotency inbox** records both event identity and processing state so redeliveries can **resume unfinished work** rather than simply "skipping if the ID was seen". That is the critical gap between **deduplication** and **workflow recovery**.

### 10.1. Why claim-only is insufficient

Consider this flawed workflow:

~~~text
1. INSERT inbox(evt-10001, status=SEEN) IF NOT EXISTS -> applied=true
2. JVM crash
3. Broker redelivers evt-10001
4. INSERT IF NOT EXISTS -> applied=false
5. App: "duplicate" -> ack and skip

Result: event is marked SEEN without persisting projections or side effects.
~~~

Never treat `applied=false` as a reason to **skip the entire workflow**. Distinguish:

| Inbox state | Meaning | Delivery/recovery handling |
|---|---|---|
| **ABSENT** | Event never seen | Eligible for LWT claim |
| **PENDING** | Claimed yet not proven all effects completed | Check owner/lease or enqueue controlled retry |
| **COMPLETED** | Contracted business steps all finished | Matching-fingerprint duplicates may safely ack |
| **CONFLICT** | Same ID with differing payload or contract violation | Quarantine/alert; never overwrite silently |
| **UNKNOWN** | Timeout or failed inbox read | Defer/reconcile; never treat as completed |

### 10.2. Illustrative inbox schema

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.event_inbox (
    tenant_id text,
    event_id text,
    payload_sha256 text,
    state text,
    owner_token text,
    lease_version bigint,
    lease_until timestamp,
    updated_at timestamp,
    PRIMARY KEY ((tenant_id, event_id))
);
~~~

This schema **optimizes lookups by event ID**, not scanning all `PENDING` rows via `WHERE state='PENDING'`. If workers must discover pending jobs independently, pair this with a **durable queue/source replay** or a dedicated **time/status-indexed table** and reconciliation. Never rely on full-table `ALLOW FILTERING` in a production scheduler.

### 10.3. Claiming a new event

~~~sql
INSERT INTO shop_integration.event_inbox
    (tenant_id, event_id, payload_sha256,
     state, owner_token, lease_version, lease_until, updated_at)
VALUES
    ('tenant-42', 'evt-10001', 'hash-A',
     'PENDING', 'worker-1:claim-abc', 0,
     '2026-11-23T03:05:00Z', '2026-11-23T03:00:00Z')
IF NOT EXISTS;
~~~

When `applied=false`, **read the existing record** and inspect fingerprint and state:

- Same fingerprint + `COMPLETED` → benign duplicate.
- Same fingerprint + `PENDING` → already claimed yet **unfinished**; apply recovery/lease rules.
- Different fingerprint → conflict.
- Timeout reading/claiming → uncertain state; defer/reconcile.

### 10.4. A state machine safer than claim-only

~~~mermaid
stateDiagram-v2
    [*] --> ABSENT
    ABSENT --> PENDING: LWT claim new event
    PENDING --> PENDING: retry/recover incomplete work
    PENDING --> COMPLETED: verify effects then conditional finalize
    PENDING --> CONFLICT: same ID, different fingerprint
    COMPLETED --> COMPLETED: same event duplicate -> ACK
    COMPLETED --> CONFLICT: same ID, different payload
~~~

Recommended sequence:

1. Receive event; validate identity and fingerprint.
2. LWT claim `PENDING` or inspect the existing row.
3. Write business events/projections/side effects using **deterministic IDs**.
4. Once all required steps are confirmed (or covered by durable recovery), transition `PENDING → COMPLETED` via conditional update.
5. Ack/commit the source only when the business contract's **completion or durable handoff criteria** are satisfied.
6. After crashes, workers or source replays resume `PENDING` entries from the **missing step**.

### 10.5. Transitioning state with CAS

~~~sql
UPDATE shop_integration.event_inbox
SET state = 'COMPLETED',
    updated_at = '2026-11-23T03:01:00Z'
WHERE tenant_id = 'tenant-42'
  AND event_id = 'evt-10001'
IF state = 'PENDING'
   AND payload_sha256 = 'hash-A';
~~~

With multiple concurrent consumers, `IF state='PENDING'` alone is **insufficient** to stop two workers from both executing side effects before finalization. Manage **`owner_token`, `lease_version`/`lease_until`, conditional claims, and fencing** so only the current lease owner can transition state. Even then, **Cassandra fencing cannot stop an external HTTP/payment provider that already accepted a request from a stale worker**—external systems must also honor idempotency tokens or fencing protocols.

### 10.6. Points where recovery must be designed explicitly

| Crash point | State | Recovery |
|---|---|---|
| Before LWT claim | `ABSENT` | Broker redelivery / producer retry |
| After claim, before business row write | `PENDING` | Durable queue/source replay or pending-index worker |
| After business row, before second projection | `PENDING` | Idempotent write of missing projection |
| After all DB rows, before marking `COMPLETED` | `PENDING` | Reconcile then finalize |
| After `COMPLETED`, before JMS/Kafka commit | `COMPLETED` | Duplicate reads inbox; skips repeating side effects |
| After external HTTP success, before saving completion | `PENDING` | Retry external call with the **same downstream idempotency key** |

**Structural limitation:** in Cassandra, a claim row, a projection row, and an external HTTP side effect represent three distinct state stores. There is no automatic "commit everything". An inbox is a **recovery protocol**, not magic turning heterogeneous resources into one ACID transaction.

### 10.7. Inbox TTL and replay windows

If an inbox row's TTL expires while an old message still sits in a broker or a backfill runs months later, the same event can be re-claimed **as brand-new**, duplicating side effects. Keep idempotency records for at least the **maximum redelivery + retention + backfill/reconciliation window**, plus operational headroom. For high-risk events, **retain records indefinitely or archive durable identities**; if legal retention forces TTL deletion, design matching replay safeguards.

**Never estimate the replay window solely from broker delivery counts**: manual DLQ replays, restores, and cross-system reprocessing frequently exceed normal redelivery schedules.

## 11. Current state by `aggregateVersion`: preventing stale regressions on late replay

An idempotent event log and an accurate **current state** are two separate problems. An order may emit:

~~~text
OrderPaid(v2, eventId=evt-10002)
OrderCancelled(v3, eventId=evt-10003)

Late retry of v2 must not regress state from CANCELLED to PAID.
~~~

### 11.1. State table and conditional update

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.order_state (
    tenant_id text,
    order_id text,
    version bigint,
    state text,
    last_event_id text,
    PRIMARY KEY ((tenant_id, order_id))
);
~~~

Initialization:

~~~sql
INSERT INTO shop_integration.order_state
    (tenant_id, order_id, version, state, last_event_id)
VALUES
    ('tenant-42', 'ORD-501', 1, 'CREATED', 'evt-10000')
IF NOT EXISTS;
~~~

Conditional transition from v1 to v2:

~~~sql
UPDATE shop_integration.order_state
SET version = 2, state = 'PAID', last_event_id = 'evt-10002'
WHERE tenant_id = 'tenant-42' AND order_id = 'ORD-501'
IF version = 1;
~~~

If v2 already applied, replaying v2 yields `applied=false`. Read back:

- `version=2, last_event_id=evt-10002` → valid duplicate retry.
- `version=3, state=CANCELLED` → v2 is stale; do not regress state.
- `version=2, last_event_id` differs → conflict/out-of-order requiring domain reconciliation.

### 11.2. Java Driver conditional statement

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement cas = SimpleStatement.builder(
        "UPDATE shop_integration.order_state "
        + "SET version = ?, state = ?, last_event_id = ? "
        + "WHERE tenant_id = ? AND order_id = ? IF version = ?")
        .addPositionalValues(
                2L, "PAID", "evt-10002", "tenant-42", "ORD-501", 1L)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL)
        .build();

boolean applied = session.execute(cas).wasApplied();
~~~

In multi-datacenter or failover topologies, evaluate **local serial consistency** scope and invariants carefully. If the business requires a single global linear order, never pick `LOCAL_SERIAL` purely for latency while ignoring cross-DC behavior.

### 11.3. Never conflate three kinds of versions

| Value | Role |
|---|---|
| `schemaVersion` | JSON/serialization contract version |
| `aggregateVersion` | Domain state transition sequence |
| `@Version` on Spring Data entity | Optimistic locking/version on persistence entity |
| Cassandra write timestamp | Last-write-wins conflict resolution |
| Kafka offset | Record position within a topic partition |

An event at aggregate version 12 can carry `schemaVersion` 3; Cassandra timestamps and Kafka offsets are separate coordinates. Never substitute `Instant.now()` for `aggregateVersion` when governing order state.

## 12. Writing multiple tables: never assume a Cassandra BATCH is an SQL transaction

In Cassandra, a single business event might update:

- `events_by_id` for ID lookup.
- `events_by_order_month` for timelines.
- `order_state` for current state.
- `event_inbox` for progress tracking.

A flow might look like:

~~~mermaid
flowchart LR
    A["Event evt-10002"] --> B["Claim / verify inbox"]
    B --> C["Upsert events_by_id"]
    C --> D["Upsert events_by_order_month"]
    D --> E["Conditional order_state"]
    E --> F["Finalize inbox"]
    F --> G["Ack source"]
~~~

If the JVM crashes after C before D, one table has the row while the other is missing it. **Never handle replay by seeing `PENDING` in the inbox and skipping**, nor treat a successful insert in `events_by_id` as proof all projections finished.

### 12.1. What does a logged batch help with?

~~~sql
BEGIN BATCH
    INSERT INTO shop_integration.events_by_id
        (tenant_id, event_id, order_id, event_type, payload_sha256)
    VALUES
        ('tenant-42','evt-10002','ORD-501','OrderPaid','hash-B');

    INSERT INTO shop_integration.events_by_order_month
        (tenant_id, order_id, bucket_month, occurred_at, event_id,
         event_type, payload_sha256)
    VALUES
        ('tenant-42','ORD-501','2026-11',
         '2026-11-23T03:01:00Z','evt-10002','OrderPaid','hash-B');
APPLY BATCH;
~~~

**`LOGGED BATCH`** (default `BEGIN BATCH` syntax) provides **batchlog recovery** to drive mutations to eventual completion under Cassandra's mechanism. Yet across **multiple partitions**, a concurrent reader may **see row A before row B** temporarily. There is no SQL snapshot isolation, no atomic JMS/Kafka commit linkage, and large multi-partition batches incur heavy overhead.

### 12.2. When to avoid batching?

For thousands of independent events spanning many partition keys, **bounded asynchronous writes** generally outperform giant multi-partition `LOGGED` batches. For a single business event producing 2–3 related mutations genuinely needing completion recovery, a **small batch** can fit. When cross-resource effectively-once guarantees are needed, **idempotency, protocols, and reconciliation** remain essential.

### 12.3. Reconciliation for self-managed materialized views

A post-crash recovery routine:

1. Retrieve the business event from a durable source or pending-indexed inbox.
2. Inspect `events_by_id` by `(tenantId, eventId)`.
3. Given a matching fingerprint, ensure the `events_by_order_month` projection exists using its **deterministic full PK**.
4. Check `order_state` by version/`eventId` without overwriting newer state.
5. Ensure external side effects via their dedicated idempotency keys.
6. Finalize the inbox once completion evidence is verified.
7. Emit metrics for repairs and conflicts; never silently drop corrupted records.

**This is eventual repair**, offering no instant cross-table transactional snapshot to readers. If clients require strict multi-table invariants, explore co-locating data within **one Cassandra partition** or choosing a transactional database suited to that constraint.

## 13. Spring Data Cassandra: entities and idempotent upserts

### 13.1. Defining composite key and entity

Matching `events_by_id` from section 3:

~~~java
import java.io.Serializable;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public record EventKey(
        @PrimaryKeyColumn(
                name = "tenant_id", ordinal = 0,
                type = PrimaryKeyType.PARTITIONED)
        String tenantId,
        @PrimaryKeyColumn(
                name = "event_id", ordinal = 1,
                type = PrimaryKeyType.PARTITIONED)
        String eventId) implements Serializable {
}
~~~

~~~java
import java.time.Instant;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("events_by_id")
public record EventRow(
        @PrimaryKey EventKey key,
        @Column("order_id") String orderId,
        @Column("event_type") String eventType,
        @Column("payload_sha256") String payloadSha256,
        @Column("occurred_at") Instant occurredAt,
        @Column("payload_json") String payloadJson) {
}
~~~

`@PrimaryKeyClass` + `@PrimaryKeyColumn(PARTITIONED)` defines the **two-part Cassandra partition key**. Java records provide value equality; if using regular classes, implement `equals`/`hashCode` accurately. `@Table` and `@Column` specify exact CQL names without relying implicitly on naming conventions.

### 13.2. Mapper preserving keys across replays

~~~java
import java.util.Objects;

public final class EventRowMapper {

    public EventRow toRow(
            OrderPaidEvent event,
            String canonicalPayloadJson) {
        Objects.requireNonNull(event, "event");
        Objects.requireNonNull(canonicalPayloadJson, "canonicalPayloadJson");

        if (event.tenantId() == null || event.tenantId().isBlank()
                || event.eventId() == null || event.eventId().isBlank()
                || event.orderId() == null || event.orderId().isBlank()
                || !"OrderPaid".equals(event.eventType())) {
            throw new IllegalArgumentException("Invalid event identity");
        }

        return new EventRow(
                new EventKey(event.tenantId(), event.eventId()),
                event.orderId(),
                event.eventType(),
                EventFingerprint.sha256(event),
                StableEventKeys.canonicalTime(event.occurredAt()),
                canonicalPayloadJson);
    }
}
~~~

`canonicalPayloadJson` must come from a serializer with a **stable contract**. If a producer sends raw JSON whose whitespace or field order varies, never treat it as canonical text assuming retries will be byte-identical. Use a versioned DTO serializer with cross-language golden tests, or store raw payloads separately while fingerprinting canonical business fields.

### 13.3. Regular upsert with `ReactiveCassandraOperations`

~~~java
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import reactor.core.publisher.Mono;

public final class EventUpsertService {
    private final ReactiveCassandraOperations operations;

    public EventUpsertService(
            ReactiveCassandraOperations operations) {
        this.operations = operations;
    }

    public Mono<Void> write(EventRow row) {
        if (row == null || row.key() == null
                || row.key().tenantId() == null
                || row.key().eventId() == null) {
            return Mono.error(new IllegalArgumentException("Missing event key"));
        }
        return operations.insert(row).then();
    }
}
~~~

`ReactiveCassandraOperations.insert(...)` returns a **reactive publisher**: creating a `Mono` performs no I/O until subscribed. Endpoints/subscribers must subscribe and handle completion/errors. Regular inserts **emit no "duplicate" signal**; if the app needs to distinguish new vs existing/conflicting events, use a conditional strategy.

### 13.4. Setting `WriteOptions` for regular upserts

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.cql.WriteOptions;

@Bean
WriteOptions immutableEventWriteOptions() {
    return WriteOptions.builder()
            .consistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .timeout(Duration.ofSeconds(3))
            .idempotent(true)
            .build();
}
~~~

Values above are **lab samples**. Use `idempotent(true)` only when events are genuinely immutable; never attach it to `UPDATE counter + 1` or list appends. `WriteOptions.timeout` is the **client-side request timeout** via the driver, not Cassandra TTL, JMS redelivery windows, or Spring gateway reply timeouts.

## 14. Spring Data Cassandra: conditional inserts and checking applied status

Modern Spring Data Cassandra offers `InsertOptions.withIfNotExists()` and `ReactiveCassandraOperations.insert(entity, InsertOptions)` returning `Mono<EntityWriteResult<T>>`, exposing `wasApplied()`.

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import org.springframework.data.cassandra.core.InsertOptions;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public final class ConditionalEventStore {
    private final ReactiveCassandraOperations operations;
    private final InsertOptions options;

    public ConditionalEventStore(ReactiveCassandraOperations operations) {
        this.operations = operations;
        this.options = InsertOptions.builder()
                .withIfNotExists()
                .consistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .serialConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_SERIAL)
                .timeout(Duration.ofSeconds(5))
                .build();
    }

    public Mono<AcceptResult> accept(EventRow incoming) {
        if (incoming == null || incoming.key() == null
                || incoming.key().tenantId() == null
                || incoming.key().eventId() == null
                || incoming.payloadSha256() == null) {
            return Mono.error(new IllegalArgumentException(
                    "Incomplete event identity/fingerprint"));
        }

        return operations.insert(incoming, options)
                .flatMap(write -> {
                    if (write.wasApplied()) {
                        return Mono.just(AcceptResult.NEW);
                    }
                    return operations.selectOneById(
                                    incoming.key(), EventRow.class)
                            .switchIfEmpty(Mono.error(
                                    new IllegalStateException(
                                            "Existing row unavailable for reconciliation")))
                            .flatMap(existing -> {
                                if (incoming.payloadSha256().equals(
                                        existing.payloadSha256())) {
                                    return Mono.just(AcceptResult.DUPLICATE);
                                }
                                return Mono.error(new IllegalStateException(
                                        "Conflicting duplicate event ID"));
                            });
                });
    }
}

enum AcceptResult { NEW, DUPLICATE }
~~~

**What this example intentionally omits:**

- Does not return HTTP status codes, commit JMS/Kafka, or trigger external side effects.
- Does not reconcile other projections; `AcceptResult.DUPLICATE` only confirms the **event row** matched the fingerprint.
- Does not handle topology outages between a failed LWT and read-back; timeouts/errors must route to recovery.
- Does not verify fingerprint algorithm versions; production must persist/check versions across migrations.
- Provides no cross-DC/linearizability guarantees beyond the chosen Cassandra CL and serial consistency.

With Cassandra LWTs, never attach custom client write timestamps as on regular `INSERT`s. **LWT can return `wasApplied=false` when replaying a previously persisted event**; that is not a network error. The service handles that via read-back. For multi-step workflows, proceed with an **inbox state machine** (section 10) rather than acknowledging solely on `DUPLICATE`.

### 14.1. When using `INSERT IF NOT EXISTS`, avoid setting idempotent blindly

Driver `setIdempotent(true)` permits retries/speculative executions. Although repeating a conditional insert never creates duplicate rows for the same primary key, the **semantic outcome** can flip from `applied=true` to `applied=false`, and downstream application branches may depend on that boolean. Enable retries/metadata only when code explicitly knows how to **reconcile** LWT outcomes without breaking side effects when attempts return different results. Never equate idempotency of **row creation** with idempotency of the **entire API call**.

## 15. Java Driver 4.x: marking statements idempotent properly

### 15.1. Prepared upsert

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

public final class EventPreparedWriter {
    private final CqlSession session;
    private final PreparedStatement insert;

    public EventPreparedWriter(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
                "INSERT INTO shop_integration.events_by_id "
                + "(tenant_id, event_id, order_id, event_type, "
                + "payload_sha256, occurred_at, payload_json) "
                + "VALUES (?, ?, ?, ?, ?, ?, ?)");
    }

    public void upsert(EventRowData row) {
        BoundStatement statement = insert.boundStatementBuilder()
                .setString(0, row.tenantId())
                .setString(1, row.eventId())
                .setString(2, row.orderId())
                .setString(3, row.eventType())
                .setString(4, row.payloadSha256())
                .setInstant(5, row.occurredAt())
                .setString(6, row.payloadJson())
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .setTimeout(Duration.ofSeconds(3))
                .setIdempotent(true)
                .build();

        session.execute(statement);
    }
}
~~~

`EventRowData` was defined in section 9. Prepared statements separate **CQL syntax** from values and are reusable inside a singleton DAO. Each incoming event gets its own **`BoundStatement`**; never share a mutable builder globally across threads.

**Important:** `setIdempotent(true)` is metadata for driver retry/speculative-execution policies; it does **not** deduplicate JMS/Kafka, block conflicting payloads, or inject `IF NOT EXISTS`.

### 15.2. Immutable statements

In Driver 4.x, statement setters return a **new statement**:

~~~java
// Wrong: returned instance is ignored.
statement.setIdempotent(true);

// Right:
statement = statement.setIdempotent(true);
~~~

This fragment assumes `statement` is a reassignable `BoundStatement` variable. Using `boundStatementBuilder()` as in section 15.1 prevents discarding setter return values.

### 15.3. Default retries and speculative execution

Per Driver 4.19 docs:

- `basic.request.default-idempotence` defaults to `false`.
- `DefaultRetryPolicy` retries only **select errors** within the request budget; it does not retry every `WRITE_TIMEOUT`.
- Speculative executions are disabled by default; if enabled, they run only for idempotent statements.
- Driver timeouts cover retries and speculative executions within the total client deadline.
- **Canceling a client request never rolls back a Cassandra mutation already dispatched.**

Never set `basic.request.default-idempotence=true` globally if the system uses counters, list appends, conditional outcomes, or operations with unguarded side effects.

## 16. Spring Integration Cassandra: from message to deterministic row

Spring Integration provides `CassandraMessageHandler` backed by `ReactiveCassandraOperations` for `INSERT`, `UPDATE`, `DELETE`, and `STATEMENT`. It acts as a one-way **outbound channel adapter** or a replying **outbound gateway**. By default the handler is **asynchronous**; synchronous waiting can be enabled via `setAsync(false)` (Java DSL `endpoint.async(false)`).

### 16.1. Preparing an application-layer mapper

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;

@Component
public final class OrderPaidRowTransformer {

    private final EventRowMapper rowMapper = new EventRowMapper();
    private final ObjectMapper objectMapper;

    public OrderPaidRowTransformer(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public EventRow map(OrderPaidEvent event) {
        try {
            // Serializer contract must be stable/versioned;
            // Application ObjectMapper requires Java Time support.
            String canonicalJson = objectMapper.writeValueAsString(event);
            return rowMapper.toRow(event, canonicalJson);
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException(
                    "Cannot serialize OrderPaidEvent", ex);
        }
    }
}
~~~

This uses the **Jackson 2** (`com.fasterxml.jackson...`) namespace common in Spring Boot 3.x projects; on Jackson 3 / Spring Boot 4, adjust APIs, namespaces, and `ObjectMapper` to match your framework version. Keep Java Time serialization, property naming/order, null inclusion, and canonicalization **consistent across deployments**, especially if `payload_json` must produce identical bytes on replay. The fingerprint in section 6 defines its own encoding to avoid depending on JSON whitespace/ordering.

### 16.2. Java DSL for idempotent entity INSERT

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.data.cassandra.core.cql.WriteOptions;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class CassandraEventFlowConfig {

    @Bean
    public IntegrationFlow immutableEventUpsert(
            ReactiveCassandraOperations operations,
            OrderPaidRowTransformer transformer,
            WriteOptions immutableEventWriteOptions) {

        return IntegrationFlow.from("validatedOrderPaidEvents")
                .transform(OrderPaidEvent.class, transformer::map)
                .handle(Cassandra.outboundChannelAdapter(
                                operations,
                                CassandraMessageHandler.Type.INSERT)
                        .writeOptions(immutableEventWriteOptions),
                        endpoint -> endpoint.async(false))
                .get();
    }
}
~~~

The flow receives `Message<OrderPaidEvent>` **already validated and tenant-authorized** before entering the channel. The `Transformer` builds `EventRow` with explicit `@Table` and `@PrimaryKey`. The adapter runs a regular upsert with `WriteOptions`. This is an **idempotent upsert approach**; it does **not detect conflicting duplicates** when two messages share an ID with differing payloads. If first-write wins and fingerprint checks are required, use the conditional service from section 14 instead of plain entity `INSERT`.

### 16.3. When conditional results are needed, never use a one-way adapter and guess

~~~text
Message<OrderPaidEvent>
   -> Transformer builds EventRow
   -> ConditionalEventStore.accept(row)
   -> Mono<AcceptResult>
      -> NEW: continue workflow
      -> DUPLICATE: check workflow/inbox state
      -> CONFLICT/DB error: quarantine/retry/reconcile
~~~

In this pattern, the **application must genuinely subscribe/await `Mono<AcceptResult>`** and connect success/error signals to the request/reply or source acknowledgment. Never call `accept(row)` and drop the publisher. If a Spring Integration endpoint handles the publisher asynchronously, ensure completion/error propagation works on your exact Spring Integration version.

**LWT `applied=false` is not an exception.** It is a conditional outcome. A one-way outbound adapter returning `send(true)` cannot tell the caller whether the result was applied, duplicate, or conflict. When callers branch on `wasApplied()`, use a replying service/gateway with an explicit contract.

### 16.4. When using a driver Statement from Spring Integration

`Cassandra.outboundChannelAdapter(operations).statementFunction(message -> Statement<?>)` can construct a CQL statement with full primary key, consistency, timeout, and idempotency settings. However, for `INSERT IF NOT EXISTS` needing `wasApplied()`, use an **outbound gateway** or a service reading the return value rather than a one-way adapter that discards conditional outcomes.

Rules of thumb:

- **Entity mode:** `@Table` entity payload; Spring Data maps columns.
- **Statement mode:** app builds values/statements and owns CQL, keys, and codecs.
- **Ingest query mode:** `List<List<?>>` matrix payload, not a JSON `String` or single entity.
- **Gateway/read:** required whenever Cassandra query results or LWT applied status matter.

### 16.5. Transformers must never re-mint business IDs

~~~java
// WRONG — each redelivery generates a new row key:
String eventId = java.util.UUID.randomUUID().toString();

// RIGHT — take from the event identity created by the producer:
String eventId = event.eventId();
~~~

`eventId` from the validated payload is the **source of truth for business identity**, never a Spring message ID generated in transit through a transformer or channel.

## 17. JMS, Kafka, HTTP: placing acknowledgments and retries after the right completion event

### 17.1. Transacted JMS listeners and synchronous completion

~~~mermaid
sequenceDiagram
    participant J as JMS Broker
    participant L as JMS listener
    participant M as DirectChannel / Transformer
    participant C as Cassandra handler sync
    participant D as Cassandra
    J->>L: Deliver evt-10001
    L->>M: Message<OrderPaidEvent>
    M->>C: Message<EventRow>
    C->>D: INSERT / LWT
    alt Operation success
        D-->>C: Completion
        C-->>L: Return
        L-->>J: Commit JMS per policy
    else Error or unknown
        D-->>C: Timeout/error
        C-->>L: Exception
        L-->>J: Rollback per policy
        J->>L: Redelivery evt-10001
    end
~~~

When the listener container uses JMS transactions over **`DirectChannel` + sync handler**, a Cassandra exception can propagate back to the listener before commit; exact rollback/redelivery behavior depends on container/broker policies.

**Cassandra writes and JMS commits remain two separate transactions.** If Cassandra persisted yet the JMS commit fails, the event redelivers and the consumer **must** be idempotent.

### 17.2. Async boundaries can forfeit redelivery

~~~text
JMS listener
  -> ExecutorChannel or Cassandra handler async=true
  -> listener returns + JMS commits
  -> Cassandra write still running
  -> DB timeout

JMS already committed: cannot roll back automatically just because DB fails later.
~~~

To process asynchronously while staying durable:

- Hand off to a **durable queue/inbox** before acknowledging the source.
- Run workers with bounded retry budgets and reconciliation.
- Never treat an **in-memory** `QueueChannel`/`ExecutorChannel` as a persistent message store.
- Preserve the original `eventId` and canonical payload.

### 17.3. Kafka offsets share no transaction with Cassandra

~~~text
Kafka poll topic=payments partition=2 offset=120
  -> Cassandra write evt-10001
  -> Observe completion
  -> Commit/ack offset per container policy
~~~

Crashing after DB success yet before Kafka offset commit triggers replay. Committing offsets before an async Cassandra write fails means Kafka **will not automatically replay committed offsets** just because Cassandra failed later.

With Kafka retry topics, per-aggregate ordering can shift; rely on immutable event logs and `aggregateVersion`/version guards when updating current state. Kafka record keys aid broker-partition ordering, yet **never guarantee asynchronous Cassandra writes finish in that exact order**.

### 17.4. HTTP retries and idempotency keys

An HTTP client may retry after a `504 Gateway Timeout`. If the endpoint mints a fresh `eventId` per HTTP retry, the backend creates multiple business events. Instead:

- Require clients to pass a unique **`Idempotency-Key`** per operation, scoped by tenant/user with an expiration contract.
- Map that key **durably** on the server to the business event ID.
- If the same key arrives with a different payload → return conflict rather than silently accepting.
- If the previous request is still `PENDING` → return pending/status lookup or resume the workflow without repeating side effects.

**Never return `202 Accepted` solely after enqueuing onto an in-memory queue** without a durable handoff. Accepted responses require a clear recovery contract.

### 17.5. Do not hide errors behind `errorChannel`

Spring Integration's `errorChannel` carries `ErrorMessage` per messaging/error-path semantics; **it is not** a JMS broker DLQ, Kafka dead-letter topic, or atomic rollback mechanism. If an error handler swallows an exception before a transacted listener sees it, the source may commit even though Cassandra never persisted.

Keep categories distinct:

- **Permanent contract errors:** invalid JSON, missing `eventId`, unauthorized tenant, codec mismatch → quarantine/DLQ with reason.
- **Transient infra errors:** Cassandra unavailable/timeout/overloaded → bounded retry/backoff/circuit breaker.
- **Unknown outcomes:** driver/server timeouts when mutations may have applied → reconcile by key/fingerprint.
- **Business conflicts:** same event ID with different payload/version → never retry like a network glitch.

## 18. Retries, timeouts, and backpressure: controlled repetition

### 18.1. A timeout does not prove the mutation did not occur

~~~mermaid
sequenceDiagram
    participant App as Consumer
    participant Drv as Java Driver
    participant C as Cassandra coordinator
    participant A as Replica A
    participant B as Replica B
    App->>Drv: INSERT evt-10001 LOCAL_QUORUM
    Drv->>C: CQL mutation
    C->>A: Write
    C->>B: Write
    A-->>C: ACK
    B-->>C: ACK
    C--xDrv: Response lost/delayed
    Drv-->>App: DriverTimeoutException
    Note over App,C: Quorum may have succeeded even though app doesn't know yet
    App->>Drv: Retry same event/key or reconcile
~~~

A thrown `DriverTimeoutException` or `WriteTimeoutException` **never implies rollback**. After a timeout, returning `FAILED` as "the database definitely did not write" is inaccurate; return **unknown/pending** or defer to reconciliation per contract.

### 18.2. Why doesn't Driver `DefaultRetryPolicy` retry every write?

Java Driver 4.x's `DefaultRetryPolicy` retries only cases judged beneficial and safe while respecting idempotence. For instance, `SIMPLE` `WRITE_TIMEOUT`s are normally **rethrown**, while `BATCH_LOG` has dedicated rules. `basic.request.timeout` is the **total client request deadline**, spanning retries and speculative executions.

Never enable `ConsistencyDowngradingRetryPolicy` to silently drop `LOCAL_QUORUM` writes to `ONE` during outages when invariants rely on quorum. Lowering CL invites stale reads, breaks read-after-write, and violates published contracts.

### 18.3. End-to-end retry budgets

~~~text
Broker JMS deliveries:      max 5
Service retries:            2 retries after first attempt
Driver possible attempts:   max 2 on certain errors

Illustrative upper bound: 5 × 3 × 2 = 30 executions/event
~~~

This is an **illustrative scenario**; not every exception triggers driver retries. With speculative executions enabled, cluster requests climb even higher.

A replay storm while Cassandra lacks capacity degrades the system further. Practice:

1. Use the driver's default retry policy for select safe failures.
2. Cap service retries with **max attempts**, jittered backoff, and deadlines.
3. Use broker delayed redelivery or durable retry topics for extended outages.
4. Bound **in-flight Cassandra operations** and concurrent source consumers.
5. Fail fast / quarantine permanent errors without burning DB retry budgets.
6. Route LWT timeouts/unknown outcomes to read-back/inbox state/reconciliation.

### 18.4. Example Reactor Retry for immutable upserts

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public Mono<Void> retryImmutableInsert(EventRow row) {
    return Mono.defer(() -> operations.insert(row).then())
            .retryWhen(
                    Retry.backoff(2, Duration.ofMillis(250))
                            .maxBackoff(Duration.ofSeconds(2))
                            .jitter(0.35)
                            .filter(CassandraRetryClassifier::isTransient));
}
~~~

This is a **method fragment** inside a service holding `ReactiveCassandraOperations operations` and an application-defined `CassandraRetryClassifier` aligned with your error taxonomy. **Never apply this to counters or non-idempotent LWT workflows**; `Retry.backoff(2,...)` runs at most **two retries after the initial attempt**. Spring Data may wrap driver exceptions in `DataAccessException`; walk the cause chain without **retrying every `RuntimeException`**.

If JMS/Kafka already handles durable retries after failure, the service may **need no Reactor retry at all**; design one coherent end-to-end policy rather than stacking hidden loops.

### 18.5. Bounded reactive writes

~~~java
import reactor.core.publisher.Flux;

// source: validated Flux<EventRow>; operations: ReactiveCassandraOperations.
Flux<EventRow> completed = source.flatMap(
        row -> operations.insert(row).thenReturn(row),
        8);
~~~

Capping at **8 in-flight requests** is a lab figure requiring real benchmarking. `flatMap` can finish **out of source order**; for current-state projections, enforce version guards or serialize by business key. Never call `subscribe()` and ack the broker before completion/error signals reach the infrastructure.

### 18.6. Circuit breakers do not replace idempotency

A circuit breaker stops flooding Cassandra during clear outages and supports fast failure/deferral. It **does not** know whether a pre-open mutation applied, perform deduplication, or turn an in-memory `QueueChannel` into a durable backlog. Separate retry and recovery workflows are still required.

## 19. Observability: measuring event effects instead of raw insert counts

| Metric/log | Measurement layer | Meaning |
|---|---|---|
| Events received / validated | Inbound/transformer | Real business ingress rate |
| Unique accepted events | Domain/inbox | Valid new event identities |
| Same-hash duplicates | Domain | Safe redeliveries/replays |
| Conflicting duplicates | Domain/security | Reused IDs or data corruption |
| Inbox `PENDING` age / count | Recovery | Claimed work awaiting finalization |
| Inbox `COMPLETED` count | Domain | Confirmed workflow completions |
| Projection mismatch count | Reconciliation | Event row exists while timeline/state lags or differs |
| Cassandra write p95/p99 latency | Driver/cluster | Throughput and tail latency |
| Driver retries / speculative executions | Driver | Request amplification |
| `Unavailable` / `ReadTimeout` / `WriteTimeout` | Cluster/driver | Availability and ACK failures |
| Driver in-flight requests / throttling | Driver | Backpressure |
| JMS queue depth / redelivery count | Broker | Upstream redelivery rate |
| Kafka consumer lag / retry-topic backlog | Broker | Downstream lag |
| DLQ/quarantine oldest age | Ops | Unresolved conflicts or permanent failures |
| LWT `applied=false` rate | Domain/cluster | Concurrent duplicates or contended IDs |
| Event retention expiry / post-expiry replays | Ops | Whether dedup window is long enough |

### 19.1. Logging traceable events without leaking data

~~~text
traceId=trace-8b2
tenantScope=tenant-42
eventId=evt-10001
operation=events_by_id_if_not_exists
fingerprintVersion=v1
businessOutcome=DUPLICATE_MATCH
inboxState=PENDING
source=jms
sourceCommitted=false
attemptScope=service
attempt=2
latencyMs=137
~~~

Never log full `payload_json`, raw authorization tokens, card/payment secrets, or sensitive bind values. `eventId` is ideal for correlating **logs and traces**, yet **must never be a per-event metric label** due to extreme cardinality.

### 19.2. Two metrics you must keep separate

**Write success rate** does not equal **business event completion rate**. One row insert can succeed while a second projection fails and the inbox stays `PENDING`. If dashboards only plot `INSERT` successes, operators falsely assume every order finished.

Track at least:

- **DB operation outcome:** success / failure / unknown.
- **Business workflow outcome:** `NEW` / `DUPLICATE` / `CONFLICT` / `PENDING` / `COMPLETED`.

### 19.3. Runbook when duplicates or conflicts spike

1. Identify which source is redelivering: JMS, Kafka offsets, HTTP clients, or backfills.
2. Verify whether `eventId` is stable or a producer is minting new IDs per retry.
3. Compare fingerprints of the same version: benign duplicate vs conflicting duplicate?
4. Inspect timeouts and driver retries: lost responses, slow coordinators, or liveness issues?
5. Check inbox states and ages: are `PENDING` items stuck without a recovery queue?
6. Measure projection mismatches and repair using deterministic row keys.
7. If hashes differ due to a serializer update, verify **canonical versions** before blaming producers.
8. During recovery, **never** replay payments or emails without downstream idempotency tokens.

## 20. Troubleshooting table

| Symptom | Possible cause | Fix |
|---|---|---|
| Redelivery creates a new row every time | Consumer uses random UUID or current bucket | Preserve producer `eventId` and original `occurredAt` |
| `INSERT` with same PK overwrites payload | Upsert/LWW; producer reused ID | Use LWT first-write wins + fingerprint conflict check |
| `IF NOT EXISTS` returns false and app skips event | Checked `SEEN` only without workflow state | Use `PENDING`/`COMPLETED` inbox + repair |
| LWT times out yet app reports definite failure | Unknown whether conditional write applied | Read back and reconcile before concluding |
| `applied=false` retried endlessly | Confused business outcome with transport error | Classify `DUPLICATE`/`CONFLICT`; do not hot-retry |
| Client times out yet row exists | Mutation applied, response lost | Preserve same ID and compare state |
| Counters double-increment | Retried non-idempotent `+1` | Use event log/dedup projection; never mark idempotent |
| List prepend creates duplicate items | Non-idempotent collection mutation | Redesign model and review retry policy |
| Retries extend TTL | Relative TTL reapplied on retry | Use stable retention/expiration policy |
| Replaying v2 overwrites v3 | Last-write-wins without version guard | Enforce CAS on `aggregateVersion` |
| Cassandra table A has row, table B lacks it | Crash between cross-table writes | Replay/reconcile projections; never treat claim as completion |
| Multi-partition logged batch treated as atomic snapshot | Misunderstood batch isolation | Design view consistency and recovery explicitly |
| Inbox `PENDING` rows stay stuck forever | Missing durable queue or pending index | Add durable discovery/replay and lease policies |
| Two workers execute the same `PENDING` event | Missing owner token/fencing | Use conditional claims, lease versions, and external idempotency |
| Inbox TTL expires and replay repeats side effects | Dedup retention window too short | Extend retention/archival to cover replay SLA |
| JMS commits before DB error | Async handler/channel did not await completion | Use durable handoff or sync completion |
| Kafka offset committed yet Cassandra timed out | Commit policy decoupled from DB completion | Align offset/ack policy + replay queue |
| Mapping errors retried endlessly | Permanent schema/codec error | Quarantine and fix contract |
| `setIdempotent(true)` has no effect | Discarded return value of immutable setter | Reassign statement or use builder |
| LWT throughput drops | Consensus overhead or hot partitions | Reserve conditionals strictly for where invariants require them |
| `tenantId` header can be spoofed | Trusted user-supplied tenant header | Verify identity/authorization before deriving keys |
| Hashes mismatch when JSON keys reorder | Hashed raw JSON bytes | Use canonical schema/version and golden tests |
| Single source reuses `eventId` across tenants | Identity lacked tenant scope | Use compound key and tenant-aware authorization |

### 20.1. Pre-deployment checklist

1. **Identity:** Producer creates `eventId` once; uniqueness scope is documented.
2. **Keys:** Full Cassandra partition/clustering keys are deterministic, including buckets/shards.
3. **Fingerprints:** Canonical fields/encoding/version defined, stored, and checked for conflicts.
4. **Write semantics:** Upsert, LWT, CAS, or inbox chosen to match invariants.
5. **TTL:** Dedup retention is at least as long as replay/backfill windows.
6. **Timestamps:** Never rely on default LWW to order business state.
7. **Side effects:** Downstream idempotency keys attached to payments, emails, and HTTP calls.
8. **Crash windows:** State after each step and resumption paths are mapped out.
9. **Source acks:** Never commit early after a purely in-memory handoff.
10. **Retries:** Bounded, jittered, and never silently downgrading consistency.
11. **Recovery:** `PENDING` discovery/durable queue, fencing, and reconciliation ready.
12. **Observability:** DB write success tracked separately from business workflow completion.
13. **Security:** Tenant authorization enforced; no raw secrets/payloads logged.
14. **Tests:** Unit mappers, CQL integration, multi-node timeouts, and broker redelivery verified.

## 21. Hands-on lab: end-to-end idempotent Cassandra writes

**Environment:** Java 17+, Spring Integration Cassandra 6+/7+ compatible with Spring Data Cassandra, Java Driver 4.x, and a Cassandra test cluster/Testcontainers. Fault-injection/quorum exercises require a multi-node cluster with real replicas; ack/replay exercises require a test JMS/Kafka broker. **Never** run `DROP`/`TRUNCATE`, kill nodes, or inject chaos in production.

### Exercise A — Unconditional upserts and conflicting duplicates

1. Create the keyspace and `events_by_id` table from section 3.
2. Write event `tenant-42 + evt-10001` with `hash-A`.
3. Send the **exact same CQL/PK and values** again; query by full `tenantId + eventId`.
4. Write again with the same PK and `hash-B`; inspect the final row values per Cassandra timestamps.
5. Explain why `INSERT` throws no default duplicate exception and why `hash-B` is a business conflict.
6. Never use `ALLOW FILTERING` to search solely by `eventId` when the table PK is `(tenantId, eventId)`.

**PASS:** One logical row exists per full PK, yet unconditional upserts do **not** enforce first-write wins.

### Exercise B — Deterministic keys across retries, replays, and timezones

1. Create an `OrderPaidEvent` with `eventId` and original `occurredAt`.
2. Use `StableEventKeys.canonicalTime/utcMonth` to derive canonical dates/buckets.
3. Resend the same event at a different processing date/time; confirm the full Cassandra key is unchanged.
4. Test an `Instant` with nanoseconds and verify truncation to milliseconds.
5. Change the JVM default timezone; confirm buckets still follow UTC.
6. Test shard versions 16 and 32; explain why changing modulo on existing data requires migration.

**PASS:** The same event always yields the same key under a fixed key-schema version regardless of retry timing.

### Exercise C — Stable fingerprints

1. Compute `EventFingerprint.sha256(...)` for a valid `OrderPaidEvent`.
2. Run 100 iterations with identical fields; confirm the hash never varies.
3. Change `amountMinor`, `currency`, `orderId`, or `eventId`; confirm the hash changes.
4. Deserialize two JSON payloads with differing field order/whitespace into the same DTO and compute hashes; confirm they match.
5. Simulate `schemaVersion=2`: design **`fingerprint:v2`** instead of silently mutating v1 fields.
6. Write golden tests with a fixed event for each language/serializer used and compare hashes.

**PASS:** Fingerprints reflect canonical business values rather than raw JSON formatting.

### Exercise D — LWT `IF NOT EXISTS` and `applied=false`

1. Run `INSERT ... IF NOT EXISTS` for a fresh event ID.
2. Verify `wasApplied()==true`.
3. Resend the same event and verify `wasApplied()==false`.
4. Read the row and compare fingerprints → `DUPLICATE_MATCH`.
5. Send the same ID with a different amount/payload; detect mismatching fingerprint → `CONFLICT`.
6. Have two concurrent writers send the same ID with different payloads; confirm only one conditional insert applies.
7. Measure LWT p99 latency against regular `INSERT` under realistic load.

**PASS:** LWT enforces first-write wins; `false` is classified by inspecting existing row content rather than treated as a network error.

### Exercise E — Spring Data Cassandra `InsertOptions`

1. Create `EventKey` and `EventRow` with `@PrimaryKeyClass`/`@PrimaryKeyColumn`.
2. Call `ReactiveCassandraOperations.insert(row, InsertOptions.builder().withIfNotExists()...)`.
3. Use `StepVerifier` or a test subscriber to inspect `EntityWriteResult<EventRow>`.
4. Verify `wasApplied()` on initial insert and replay.
5. On `applied=false`, read back via `selectOneById(row.key(), EventRow.class)`.
6. Simulate a failure where read-back returns empty; do not blindly mark as duplicate.
7. Verify null/codec/primary-key mapping against real Cassandra.

**PASS:** Goes beyond mocking API call counts; verifies round-trip keys/fields and LWT outcomes.

### Exercise F — TTLs and write timestamps

1. Create a **test table** with a default TTL or use CQL `USING TTL`.
2. Write a row with a short TTL in the test environment and inspect `TTL(column)` where applicable.
3. Resend the same PK/values after a pause; compare remaining TTL/expiration.
4. Write two conflicting updates on the same key with controlled timestamps; observe LWW.
5. Replay an older event after a newer state event; do not rely on write timestamps to preserve aggregate ordering.
6. Verify why custom write timestamps are disallowed/ignored on LWT conditional statements.

**PASS:** Explains how temporal idempotency differs from logical-row idempotency.

### Exercise G — Inbox crash right after claim

1. Create `event_inbox` from section 10.
2. LWT-claim `PENDING` for `evt-10001`.
3. Simulate a crash **before** writing the business projection.
4. Let the broker redeliver; LWT claim returns `false`.
5. **Do not skip**: read `PENDING` and resume via the durable retry/recovery path.
6. Write the business row and finalize `COMPLETED` with an appropriate CAS.
7. Redeliver the same event again; see `COMPLETED` + matching hash and ack safely.

**PASS:** No business effects lost due to "claim already existed"; workflow resumes cleanly after crash.

### Exercise H — Two workers and fencing

1. Run two workers receiving `evt-10002` simultaneously.
2. Attempt concurrent LWT claims and confirm only one gets `applied=true` from `ABSENT`.
3. Have Worker A hold the lease and stall until the lease expires.
4. Allow Worker B to acquire a new lease via **conditional claim/version**.
5. Wake Worker A to attempt state finalization; owner/version CAS must block A from corrupting the inbox.
6. If A already called an external HTTP API, verify **downstream idempotency tokens** protect it since Cassandra fencing cannot recall sent requests.

**PASS:** Distinguishes CAS fencing of inbox state from idempotency of external side effects.

### Exercise I — Writing multiple Cassandra tables and reconciliation

1. Create `events_by_id` and `events_by_order_month` with keys from section 12.
2. Persist the ID row, then intentionally stop before writing the timeline.
3. Verify one table has data while the other does not.
4. Replay/repair using the exact same timeline full PK without minting another `eventId`.
5. For current-state projections, enforce a version guard to prevent state regression.
6. Transition inbox to `COMPLETED` only after verifying required steps.
7. Run a small multi-partition `LOGGED` batch in tests and note the possibility of partial visibility.

**PASS:** Reconciliation repairs missing steps without claiming multi-table SQL atomicity.

### Exercise J — Spring Integration JMS/Kafka acknowledgment

1. Configure a transacted JMS source or test Kafka consumer with explicit ack/offset settings.
2. Route `Message<OrderPaidEvent>` → transformer → `EventRow` → `async(false)` Cassandra handler over `DirectChannel`.
3. Let Cassandra succeed, then simulate a JVM crash before JMS/Kafka offset commit.
4. Observe broker replay of the event with **the same ID**; projections add no second business row.
5. Switch to `ExecutorChannel` or an async handler and observe that the source **can commit before DB completion**.
6. Add a durable handoff/retry queue and error propagation for the async path.
7. Send malformed/unauthorized payloads; verify DLQ/quarantine handling rather than endless DB retries.

**PASS:** Knows precisely when the source acks/commits and when durable replay is required.

### Exercise K — Retry storms, timeouts, and backpressure

1. Measure baseline Cassandra p50/p95/p99 on a healthy cluster.
2. Raise bounded concurrency and inject timeout faults in tests.
3. Enable driver `DefaultRetryPolicy` plus a capped service retry; observe request amplification.
4. Confirm `DriverTimeoutException` **does not prove** the mutation never ran.
5. Re-test with upstream concurrency throttling, jittered backoff, and circuit breakers.
6. Count business `NEW`/`DUPLICATE`/`CONFLICT`/`PENDING`/`COMPLETED` outcomes rather than just DB inserts.
7. Verify timeouts never break inbox/broker recovery paths.

**PASS:** Retries are recoverable, observable, free of load storms, and preserve data accuracy.

### Exercise L — Migrations, replay windows, and security checks

1. Create test events with `schemaVersion=1` and fingerprint v1.
2. Introduce schemaVersion/fingerprint v2 and test the same business identity across compatibility rules.
3. Send the same event ID from two distinct tenants; verify full PKs stay isolated per tenant.
4. Send a spoofed `tenantId` header; confirm authorization blocks it before key derivation.
5. Configure a short inbox TTL **in lab only**, let it expire, and replay; observe the risk of re-claiming as a new event.
6. Document a production retention policy derived from the maximum replay/backfill window.
7. Inspect logs/metrics to confirm no raw payment details or per-event ID metric labels appear.

**PASS:** Keys/fingerprints are versioned, tenant isolation holds, and dedup windows match replay SLAs.

### Final verification matrix

| Check | PASS when |
|---|---|
| Business ID | Unchanged across producer retries, JMS/Kafka replays, and backfills |
| PK/partition key | Same event → same full key, including buckets/shards |
| Canonical fingerprint | Same semantic payload → same digest |
| Conflict | Same ID / different payload rejected and investigated |
| Regular upsert | No extra rows for same PK; LWW understood |
| TTL | Understands retries can shift expiration |
| LWT | `wasApplied()` true/false/timeout handled distinctly |
| Inbox `PENDING` | Never acked/skipped before side effects are complete/durable |
| Inbox CAS/fencing | Stale workers blocked from corrupting finalization |
| Current state | Older `aggregateVersion` never overwrites newer version |
| Multi-table | Reconciliation in place; no instant atomic snapshot assumed |
| Java Driver | Idempotency flag not applied blindly; timeouts/CL exact |
| Spring Data | Entity mapping and `InsertOptions` accurate |
| Spring Integration | Transformers and sync/async handlers used intentionally |
| JMS/Kafka | Source commit/offset never assumed atomic with Cassandra |
| Retries/backpressure | Bounded, jittered, and never retrying permanent contract failures |
| Security | Tenant scope verified; no raw secrets logged |
| Observability | DB operation success separated from business completion |

**Limitations of unit mocks:** a mocked `ReactiveCassandraOperations` cannot prove Cassandra LWT consensus, server/driver timeouts, coordinator failover, batchlog recovery, or JDBC-like transaction semantics. Those require **real Cassandra** in tests; JMS/Kafka acknowledgment checks require an actual broker and controlled fault injection.

## 22. Self-assessment questions

1. Why can JMS/Kafka at-least-once delivery process the same business event multiple times even when the producer made no mistake?
2. How does CQL statement idempotence differ from business event idempotency?
3. Why aren't "running `INSERT` literally once" and "processing an event with once-only effects" the same concept?
4. Is an unconditional Cassandra `INSERT` a unique insert or an upsert?
5. If two different payloads share the same full primary key, what can happen to regular columns?
6. Why include `tenantId` in the key when `eventId` is unique only within each tenant?
7. How does a business `eventId` differ from `JMSMessageID`, Kafka offsets, and Spring Message IDs?
8. When should the producer create `eventId`, and which ID must client retries reuse?
9. Why must consumers never call `UUID.randomUUID()` on every retry as the Cassandra PK?
10. Why does computing `bucket_month` from current processing time create duplicates on replay?
11. How do `Instant` and CQL `timestamp` differ in precision?
12. If shard count rises from 16 to 32, why can keys for historical data shift?
13. Can raw JSON hashes change even when semantic fields stayed identical? Give an example.
14. Which business fields should a payload fingerprint include to catch conflicting duplicates?
15. Why must canonical fingerprint algorithms be versioned?
16. Do matching `eventId` and matching fingerprint always mean all downstream effects finished?
17. Which invariant does LWT `INSERT IF NOT EXISTS` help enforce?
18. How should `wasApplied()=false` be handled to distinguish duplicates from conflicts?
19. Does a timeout during LWT conditional insert prove the row does not exist yet?
20. Why are `LOCAL_SERIAL` and `LOCAL_QUORUM` two distinct settings in an LWT?
21. Why shouldn't custom `USING TIMESTAMP` be attached to an LWT?
22. When is a regular deterministic upsert enough, and when is LWT first-write wins needed?
23. Why can using LWT on every single event hurt throughput?
24. Can Cassandra `USING TTL` extend an event's lifespan across retries?
25. Is a Cassandra write timestamp equivalent to a domain `aggregateVersion`?
26. Why can replaying `OrderPaid(v2)` regress state after `OrderCancelled(v3)`?
27. How does compare-and-set `UPDATE ... IF version = ?` enforce ordering?
28. How do `schemaVersion`, `aggregateVersion`, `@Version`, and Kafka offsets differ?
29. Are counter updates (`+1`) idempotent? Why or why not?
30. Why are list prepends dangerous under automatic driver retries?
31. Does Java Driver's `setIdempotent(true)` create a unique key or deduplication record?
32. Why avoid enabling `basic.request.default-idempotence=true` system-wide when counters or external side effects exist?
33. How must Java Driver's immutable statement setters be used?
34. Why doesn't `DriverTimeoutException` imply a Cassandra rollback?
35. What bug does a `SEEN`-only inbox cause if the JVM crashes right after claiming?
36. How do `PENDING` and `COMPLETED` states differ in a durable inbox?
37. If inbox rows are partitioned solely by `eventId`, how can workers find all `PENDING` work without a full-table scan?
38. Lease/version fencing stops stale workers from writing the inbox, yet which external side effect can it not stop?
39. Why does an external payment provider also need an idempotency token?
40. Which kinds of replay windows must inbox TTL account for?
41. Does a multi-partition logged batch guarantee snapshot isolation across two Cassandra tables?
42. Why is reconciliation needed for `events_by_id` and `events_by_order_month` after a crash?
43. When Cassandra writes successfully yet the JMS commit fails, what can the broker do?
44. When JMS commits early before an async Cassandra failure, why can't the error roll back the source?
45. Is a Kafka offset commit atomic with a Cassandra mutation?
46. Is Spring Integration's `CassandraMessageHandler` synchronous or asynchronous by default?
47. With Spring Integration's one-way adapter, can you rely on `send(true)` to know LWT `wasApplied()`?
48. What result can `ReactiveCassandraOperations.insert(row, InsertOptions)` return for a conditional insert?
49. Why shouldn't you ack a duplicate event immediately upon seeing the event row if projections or emails remain?
50. How should a retry budget coordinate driver, service, and broker layers to avoid request amplification?
51. Does an `ErrorMessage` arriving on Spring Integration's `errorChannel` mean it entered a JMS DLQ?
52. Which metrics separate database write success from business workflow completion?
53. Why avoid using `eventId` as a per-event metric label?
54. When a producer sends the same ID with a different hash, should the app retry the database or report a domain conflict?
55. Propose a recovery plan for a `PENDING` event that wrote table A before crashing prior to table B, while a newer state version has already arrived.

## 23. Official references

- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): `INSERT` upserts, `IF NOT EXISTS`, `UPDATE`, `BATCH`, TTL, timestamps, and counter semantics.
- [Apache Cassandra — CQL Data Types](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/types.html): `timestamp`, `uuid`, `counter`, collections, and typed data.
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html): query-first partition-key design and controlling partition growth.
- [Apache Cassandra — Dynamo Architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html): tunable consistency, replication, quorum, and conflict resolution.
- [Apache Cassandra Java Driver 4.19 — Idempotence](https://apache.github.io/cassandra-java-driver/4.19.0/core/idempotence/): `Statement.setIdempotent(...)`, default false, and conditions for safe retries/speculative execution.
- [Apache Cassandra Java Driver 4.19 — Retries](https://apache.github.io/cassandra-java-driver/4.19.0/core/retries/): `DefaultRetryPolicy` and safe retry decisions.
- [Apache Cassandra Java Driver 4.19 — Query Timestamps](https://apache.github.io/cassandra-java-driver/4.19.0/core/query_timestamps/): timestamp generators, `setQueryTimestamp(...)`, and LWT restrictions.
- [Apache Cassandra Java Driver 4.19 — Speculative Execution](https://apache.github.io/cassandra-java-driver/4.19.0/core/speculative_execution/): idempotent-only scope, request amplification, and cancellation semantics.
- [Apache Cassandra Java Driver 4.19 — Statements](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/): immutable statements, CL, timeouts, and query timestamps.
- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html): `@Table`, `@PrimaryKeyClass`, `@PrimaryKeyColumn`, and converter metadata.
- [Spring Data Cassandra — Persisting Entities](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): `ReactiveCassandraOperations`, `InsertOptions`, `UpdateOptions`, upserts, and LWTs.
- [Spring Data Cassandra API — InsertOptionsBuilder](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/InsertOptions.InsertOptionsBuilder.html): `withIfNotExists()`, consistency, serial consistency, and timeouts.
- [Spring Data Cassandra API — EntityWriteResult](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/EntityWriteResult.html): `wasApplied()` via `WriteResult` and entity results.
- [Spring Data Cassandra API — ReactiveCassandraOperations](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/ReactiveCassandraOperations.html): reactive insert/select/conditional operations.
- [Spring Integration — Apache Cassandra Support](https://docs.spring.io/spring-integration/reference/cassandra.html): `CassandraMessageHandler`, outbound adapter/gateway, `statementFunction`, async default, and `writeOptions`.
- [Spring Integration — Message Transformation](https://docs.spring.io/spring-integration/reference/transformer.html): `Transformer` before persistence handlers.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `errorChannel`/`ErrorMessage` and synchronous/asynchronous behavior.
- [Spring Integration — JMS](https://docs.spring.io/spring-integration/reference/jms.html): message-driven inbound adapters, JMS containers, and transaction considerations.
- [Spring Integration — Kafka](https://docs.spring.io/spring-integration/reference/kafka.html): Kafka inbound adapters/gateways, error handling, and offset boundaries.
- [Project Reactor — Retry](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html#_retrying): `retryWhen`, backoff, and error classification.

**Key takeaway:** Designing idempotent Cassandra writes starts with an **immutable business event ID**, **deterministic full Cassandra keys**, and a **versioned payload fingerprint**. Regular `INSERT` is an **upsert**—it neither protects first-write wins nor detects conflicting duplicates; when needed, use `INSERT IF NOT EXISTS`/LWT and check `wasApplied()` **paired with read-back**. **Timeouts never prove data wasn't written**; retries must be bounded and applied only to truly safe operations. Never treat a `SEEN`/`PENDING` row, a multi-partition logged batch, or `send(true)` as proof every side effect succeeded. In Spring Integration over JMS/Kafka/HTTP, combine **explicit acknowledgment boundaries, durable inbox/replay, conditional state transitions, downstream idempotency, and reconciliation** to recover accurately across crashes, concurrent deliveries, and reprocessing.








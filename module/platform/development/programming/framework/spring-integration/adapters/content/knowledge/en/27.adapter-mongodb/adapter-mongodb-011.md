# Handling Duplicate Keys and Retries in Spring Integration MongoDB

## Learning Objectives

After this lesson, you will be able to:

- Explain the **MongoDB E11000 duplicate key** error (typically error code `11000`), why it occurs when `insert`, `upsert`, `update`, or bulk operations violate a unique index, and how Spring Data translates it into `DuplicateKeyException`.
- Distinguish between **duplicate message delivery**, **valid repeated business requests**, **ID conflicts with differing content**, and **duplicates caused by flawed unique index design**; never treat every duplicate as success.
- Design business idempotency keys stable across retries/restarts, scope keys by tenant/source, and use MongoDB's `_id` or compound unique indexes to arbitrate races.
- Compare `insert`, `save`, `upsert`, `updateFirst`, `findAndModify`, and `insertMany`/`bulkWrite` regarding duplicate/error semantics.
- Build a Spring Integration handler receiving messages from HTTP/JMS/AMQP/Kafka/file/SFTP, writing to a MongoDB inbox, and classifying outcomes as **INSERTED / ALREADY_ACCEPTED / CONFLICT**.
- Explain how **MongoDB driver Retryable Writes** differ from **Spring Integration `RequestHandlerRetryAdvice` / Spring Retry** and from broker redelivery.
- Classify **transient errors** (network, failover, timeouts, resource contention) vs. **permanent errors** (unique conflicts, schema, auth); configure retries with max attempts, exponential backoff, jitter, and recovery channels.
- Handle cases where **MongoDB wrote successfully but the response/ACK was lost**, causing a subsequent retry to hit E11000; reconcile using the same event ID and payload instead of generating a new key.
- Understand retry boundaries within MongoDB transactions, including `TransientTransactionError`, `UnknownTransactionCommitResult`, and why not every duplicate-key error is automatically retried.
- Design dead-letter/quarantine, transactional outbox/inbox, ACK policies, observability, graceful shutdown, and tests for concurrency, duplicates, timeouts, and restarts.

This lesson belongs to the **Adapter MongoDB** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module connects external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practicing integration with files, SFTP, HTTP, JMS, AMQP, Kafka, and databases while handling message contracts, errors, and connection lifecycles. The focus here is **correctness when data is re-sent or written concurrently by multiple workers**: a duplicate-key error is both a uniqueness safeguard and a signal that a valid request may already have been processed.

> **Version scope:** examples use Java 17+, Spring Boot 3.x, Spring Data MongoDB, Spring Integration 6.x, and Spring Retry 2.x aligned via the project's BOM. APIs in Spring Integration 7.x or newer Spring Retry versions may vary; verify against your actual dependencies. `mongosh` examples target a test database only—never run them against production data.

## 1. Problem: Source Re-Sends the Same Event, Yet the Database Errors

A device sends an event over HTTP or Kafka:

~~~json
{
  "tenantId": "tenant-a",
  "eventId": "evt-1001",
  "deviceId": "node-7",
  "sequence": 1001,
  "temperatureC": 26.5,
  "occurredAt": "2026-11-23T02:00:00Z"
}
~~~

On first delivery, the app successfully writes to MongoDB's `event_inbox`. Immediately after the write, the connection drops so the producer **receives no acknowledgment**. The producer or broker redelivers **the same event**.

~~~mermaid
sequenceDiagram
    participant P as Producer / Broker
    participant I as Spring Integration
    participant M as MongoDB
    P->>I: evt-1001
    I->>M: insert(_id=tenant-a|evt-1001)
    M->>M: write succeeds
    M--xI: ACK lost / timeout
    Note over P: Unacknowledged
    P->>I: redelivery evt-1001
    I->>M: insert(same _id)
    M-->>I: E11000 duplicate key
    I->>M: readback by _id, compare content
    M-->>I: content matches identically
    I-->>P: ALREADY_ACCEPTED, per ACK policy
~~~

**Read the diagram carefully:** E11000 on the second write does not necessarily mean the original request failed. If the record already exists **and its business content genuinely matches**, the redelivery can be an **idempotent repeat**. If the ID matches while amount/device/content differ, that is a **business conflict** that must be flagged.

### 1.1. Outcomes to Distinguish

| Scenario | Processing outcome | Immediately retry the raw insert? |
|---|---|---|
| ID absent, insert succeeds | `INSERTED` | No |
| ID exists, equivalent payload, durably accepted | `ALREADY_ACCEPTED` | Not needed |
| ID exists with differing payload | `CONFLICT` | **No**; alert/quarantine |
| E11000 from an **index other than `_id`** | `CONFLICT` or data model issue | **No** blind retry |
| Network timeout, uncertain whether insert occurred | `UNKNOWN` → reconcile / bounded retry | Possibly, **keeping same ID** |
| MongoDB unavailable | `TRANSIENT_FAILURE` | Yes, under retry policy |
| Mapping/schema validation failure | `INVALID_MESSAGE` | No; fix upstream data |
| Duplicate after consumer already committed | `ALREADY_PROCESSED` per business state | Never trigger side effects twice |

**Never label all of the above generically as `SUCCESS`.** "Persisted to inbox" and "published to Kafka" or "payment settled" are **different business stages**.

## 2. Where Does E11000 Duplicate Key Come From?

In MongoDB, every collection has a default unique index on `_id`. Applications can add unique indexes on other business keys. When an insert or update violates a value guarded by a unique index, the server returns an error like:

~~~text
E11000 duplicate key error collection: lab.event_inbox
index: _id_ dup key: { _id: "tenant-a|evt-1001" }
~~~

The server error code is typically **`11000`**. In Spring Data MongoDB via `MongoTemplate`/`MongoOperations`, it is translated into:

~~~java
org.springframework.dao.DuplicateKeyException
~~~

This is a subclass of `DataIntegrityViolationException` in Spring's DAO exception hierarchy. With the raw MongoDB Java driver, you may see `MongoWriteException` or `MongoBulkWriteException` carrying write error code `11000`; **do not** assume every code path throws the exact same Spring DAO exception directly.

### 2.1. Why Errors Do Not Happen Only on Insert

| MongoDB operation | When can E11000 occur? | Note |
|---|---|---|
| `insertOne` / `MongoOperations.insert` | Duplicate `_id` or unique business key | Suitable for immutable event logs |
| `insertMany` / `bulkWrite` | One or more documents violate a unique index | Can partially succeed without a transaction |
| `save` with existing `_id` | May **replace** the document, yet can still violate **another unique index** | Never use `save` to prevent duplicate messages |
| `updateOne` / `updateFirst` | Updating a field collides with another document's unique key | Not necessarily caused by a duplicate event |
| `upsert` | Insert branch collides with a unique constraint, or worker race | Some cases receive special server handling; never rely on it |
| `findAndModify` + upsert | Upsert creates a new doc violating an index | Requires compatible query/unique keys |
| Creating a unique index on existing data | Collection already holds duplicate values | Index build fails |
| Replacing a document with new fields | Unique index on a newly set field collides | Match the exact index name |

### 2.2. E11000 Does Not Automatically Mean "Same Event Already Exists"

A collection might carry two unique indexes simultaneously:

~~~javascript
db.event_inbox.createIndex(
  { tenantId: 1, eventId: 1 },
  { unique: true }
)

db.event_inbox.createIndex(
  { tenantId: 1, deviceId: 1, sequence: 1 },
  { unique: true }
)
~~~

Suppose `eventId=evt-2001` does not exist yet, while `(tenant-a, node-7, sequence=1001)` already belongs to `evt-1001`: the new insert fails with E11000 from **the second index**. Therefore, when catching `DuplicateKeyException`:

1. Use the **stable business key** to read back the existing record.
2. Compare tenant, `eventId`, and canonical content.
3. If no record exists with that ID yet E11000 occurred, suspect **another index or data conflict**.
4. Never assume every duplicate should be ACKed as success.

## 3. Unique Indexes and Business Key Design

### 3.1. Prefer IDs Stable Across Retries

A business event ID must be:

- Generated **once** per logical event by the producer or ingress layer.
- Preserved across broker redeliveries, HTTP retries, MongoDB driver retries, and application retries.
- Scoped clearly by tenant/source/event type as needed.
- Never based on a fresh Spring `MessageHeaders.ID` per dispatch.
- Never a newly generated `UUID.randomUUID()` on every write attempt of the same event.

Example namespaced MongoDB `_id` for the lab:

~~~java
String mongoId = tenantId + "|" + eventId;
~~~

**Production must validate** `tenantId`/`eventId` and enforce escaping/length rules to avoid collisions: `tenant-a|x` + `y` must never collide logically with another ID pair via separator characters. Use a canonical encoded ID or a compound unique index.

### 3.2. Compound Unique Index

`mongosh` example:

~~~javascript
use integration_lab

db.event_inbox.createIndex(
  { tenantId: 1, eventId: 1 },
  {
    unique: true,
    name: "uq_tenant_event"
  }
)
~~~

Use this unique index when `eventId` is unique only **within a tenant**. If `eventId` is globally unique, `_id` alone may suffice.

Testing:

~~~javascript
db.event_inbox.insertOne({
  _id: "doc-1", tenantId: "tenant-a",
  eventId: "evt-1001", status: "RECEIVED"
})

db.event_inbox.insertOne({
  _id: "doc-2", tenantId: "tenant-a",
  eventId: "evt-1001", status: "RECEIVED"
})
// Second command triggers duplicate key on uq_tenant_event.
~~~

**Never run seeds repeatedly on production.** Isolate test databases/collections. Building a unique index on a collection containing duplicates will fail; audit and clean duplicates first.

### 3.3. Nulls, Missing Fields, and Partial Unique Indexes

A **single-field unique index** typically permits at most **one entry** with `null` or missing value for that field. Compound unique indexes also enforce rules over combinations of null/missing values. If legacy records lack `eventId`, adding a unique index can cause unrelated inserts to hit E11000.

In a business collection with mixed schemas:

~~~javascript
db.event_inbox.createIndex(
  { tenantId: 1, eventId: 1 },
  {
    unique: true,
    name: "uq_tenant_event_valid",
    partialFilterExpression: {
      tenantId: { $type: "string" },
      eventId: { $type: "string" }
    }
  }
)
~~~

**This is a test-data policy example only**, not an excuse to accept missing IDs in idempotent workflows. A partial index enforces uniqueness **only for documents matching the filter**; documents outside the filter **receive no uniqueness protection from that index**. For production inboxes requiring `eventId`, validate schemas/IDs before insert and migrate legacy data.

### 3.4. Unique Index Limitations on Sharded Collections

On MongoDB sharded clusters, unique indexes carry shard-key restrictions. Never assume a unique index on `eventId` is enforced **cluster-wide** unless it complies with shard-key prefix rules. Design tenant/shard keys and unique indexes together, consulting the MongoDB Manual for your exact version/topology.

### 3.5. Indexes Differ from Query Performance

Unique indexes enforce data constraints, yet:

- Add write, memory, and disk overhead.
- Do not replace rate limiting or backpressure.
- Do not replace tenant API authorization.
- Cannot fix a race via naive `if (!exists) insert`; **the unique index is the final arbiter**.

## 4. Differences Among insert, save, upsert, and findAndModify

### 4.1. insert: Duplicate Errors Detect Redelivery

~~~java
mongoOperations.insert(event, "event_inbox");
~~~

For immutable events, `insert` is straightforward: **absent → inserted; present → E11000**. After catching the error, the service reads back by business key to distinguish a valid duplicate from a conflict.

### 4.2. save: Not an "Ignore Duplicate" Tool

~~~java
mongoOperations.save(event, "event_inbox");
~~~

When a document shares the same ID, `save` can **replace** the existing document instead of reporting a duplicate. This is dangerous if an old message is redelivered after the document already reached `DONE`: saving the old payload can reset status back to `NEW` or overwrite newer business fields.

**Never use `save` as an idempotent inbox insert** if state or fields can evolve after the initial write. When replacement/upsert is truly intended, enforce versioning/optimistic locking.

### 4.3. Conditional Updates Without Prior Reads

To mark an event processed:

~~~java
Query query = Query.query(
    Criteria.where("_id").is(id)
            .and("status").is("PROCESSING")
            .and("claimOwner").is(workerId));

Update update = new Update()
    .set("status", "DONE");

UpdateResult result = mongoOperations.updateFirst(
    query, update, "event_inbox");

boolean changed = result.getMatchedCount() == 1;
~~~

This fragment needs `Query`, `Criteria`, `Update`, `UpdateResult` imports and a `MongoOperations` bean. Conditional updates prevent a stale worker from marking `DONE` after losing its claim. Still verify **business commit succeeded before marking `DONE`**.

### 4.4. findAndModify for Atomic Claiming

~~~java
Query eligible = Query.query(
    Criteria.where("status").is("NEW"))
    .with(Sort.by(
        Sort.Order.asc("createdAt"),
        Sort.Order.asc("_id")));

Update claim = new Update()
    .set("status", "PROCESSING")
    .set("claimOwner", workerId)
    .set("leaseUntil", leaseDeadline);

InboxEvent claimed = mongoOperations.findAndModify(
    eligible, claim,
    FindAndModifyOptions.options().returnNew(true),
    InboxEvent.class, "event_inbox");
~~~

An atomic conditional `findAndModify` on one document prevents two workers from winning the claim on the same `status=NEW` document concurrently. You still need **lease expiry/reclaim, fencing/versions, retries, and idempotency** when workers die.

### 4.5. Upsert and Races

`update(..., upsert=true)` creates records if absent, yet is not an automatic idempotency protocol for every business request. If two workers upsert concurrently on filters incompatible with unique indexes or mutate unique fields, duplicate-key errors occur. Starting in MongoDB **8.1**, an upsert causing a duplicate-key error inside a **multi-document transaction** is not automatically retried by the server per documented behavior. Never write infinite retry loops on `DuplicateKeyException` expecting it to "go away".

## 5. Outcome Contract: Inserted, Already Accepted, Conflict

A reliable ingest API should define business outcomes clearly:

| Outcome | When? | Should the source be ACKed? |
|---|---|---|
| **INSERTED** | MongoDB insert confirmed and record exists in durable inbox | Can ACK if contract only requires inbox durability |
| **ALREADY_ACCEPTED** | Record with same ID **and matching business content** was already accepted | Usually safe to ACK again if durability/state still holds |
| **CONFLICT** | Same ID with different content, or another unique index collided | Never treat as success; send to DLQ/quarantine or return HTTP 409 |
| **RETRYABLE_FAILURE** | DB temporarily unavailable or transient network error | Do not ACK early; bounded retry |
| **UNKNOWN_OUTCOME** | Timeout/lost response, outcome unknown | Reconcile with same ID before deciding |
| **INVALID_MESSAGE** | Missing tenant/`eventId`, bad schema/size | Never retry as a transient error |

**A duplicate may be ACKed as idempotent success only after content verification**, and only within the scope of "durably received". If the client needs proof of "payment settled", inspect downstream business completion rather than just the inbox record.

## 6. Project Setup and Demo Data

### 6.1. Maven Dependencies

With Spring Boot 3.x and Spring Integration 6.x via a compatible BOM:

~~~xml
<!-- Dependencies inside <dependencies> -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-mongodb</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.retry</groupId>
    <artifactId>spring-retry</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

This is a blocking example. Reactive MongoDB requires `spring-boot-starter-data-mongodb-reactive`/`ReactiveMongoOperations`, Reactor, and reactive retry operators. Never override BOM versions manually without testing.

### 6.2. Lab URI

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://127.0.0.1:27017/integration_lab
~~~

Unauthenticated local MongoDB is for labs only. Production requires secret management/TLS, least privilege, appropriate write concerns, timeouts/pools, health checks, and isolated databases/collections. MongoDB Retryable Writes require a replica set or sharded cluster and do not work identically on standalone instances.

### 6.3. Domain Event and Inbox Record

~~~java
package example.mongoingest;

import java.math.BigDecimal;
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

public record IncomingTelemetry(
        String tenantId,
        String eventId,
        String deviceId,
        long sequence,
        BigDecimal temperatureC,
        Instant occurredAt) {
}

@Document(collection = "event_inbox")
public record InboxEvent(
        @Id String id,
        String tenantId,
        String eventId,
        String deviceId,
        long sequence,
        @Field(targetType = FieldType.DECIMAL128)
        BigDecimal temperatureC,
        Instant occurredAt,
        String status,
        Instant receivedAt) {
}
~~~

In real Java projects, place each public top-level type in its own `.java` file or adjust visibility per package layout. `@Field(targetType=DECIMAL128)` preserves decimal precision in BSON Decimal128; test exact converter/schema behavior. Never compare `status` or `receivedAt` when checking event content equality because they are **mutable metadata** differing across deliveries.

### 6.4. Seeding/Testing Unique Indexes

~~~javascript
use integration_lab

db.event_inbox.createIndex(
  { tenantId: 1, eventId: 1 },
  { unique: true, name: "uq_tenant_event" }
)

db.event_inbox.createIndex(
  { tenantId: 1, deviceId: 1, sequence: 1 },
  { unique: true, name: "uq_tenant_device_sequence" }
)
~~~

Create indexes in migrations before traffic starts; never create/drop indexes while requests are retrying. Never auto-create unique indexes in production without auditing existing data. If the second index is not a true business invariant (e.g., devices can emit corrected events with the same sequence), **do not create it**; this lesson uses it to illustrate E11000 from a secondary index.

## 7. Idempotent Handler: Insert Then Read Back the Record

### 7.1. Outcome Enum and Conflict Exception

~~~java
package example.mongoingest;

public enum IngestOutcome {
    INSERTED,
    ALREADY_ACCEPTED
}
~~~

~~~java
package example.mongoingest;

public final class IngestConflictException
        extends RuntimeException {
    public IngestConflictException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

### 7.2. Service Handling Duplicates Explicitly

~~~java
package example.mongoingest;

import java.time.Instant;
import java.math.BigDecimal;
import java.util.Objects;

import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.stereotype.Service;

@Service
public class MongoInboxIngestService {

    private final MongoOperations mongo;

    public MongoInboxIngestService(MongoOperations mongo) {
        this.mongo = mongo;
    }

    public IngestOutcome ingest(IncomingTelemetry input) {
        validate(input);

        // Use the exact same ID across all retries/redeliveries.
        String id = input.tenantId() + "|" + input.eventId();

        InboxEvent candidate = new InboxEvent(
            id,
            input.tenantId(),
            input.eventId(),
            input.deviceId(),
            input.sequence(),
            input.temperatureC(),
            input.occurredAt(),
            "RECEIVED",
            Instant.now());

        try {
            mongo.insert(candidate, "event_inbox");
            return IngestOutcome.INSERTED;
        } catch (DuplicateKeyException duplicate) {
            InboxEvent existing = mongo.findById(
                id, InboxEvent.class, "event_inbox");

            // Same _id yet record not found or content mismatches:
            // may stem from another index, race, read consistency,
            // or business conflict. Never ACK as success.
            if (existing == null || !sameBusinessEvent(
                    input, existing)) {
                throw new IngestConflictException(
                    "Event identity/content conflict", duplicate);
            }

            return IngestOutcome.ALREADY_ACCEPTED;
        }
    }

    private static boolean sameBusinessEvent(
            IncomingTelemetry input, InboxEvent stored) {
        return Objects.equals(input.tenantId(), stored.tenantId())
            && Objects.equals(input.eventId(), stored.eventId())
            && Objects.equals(input.deviceId(), stored.deviceId())
            && input.sequence() == stored.sequence()
            && stored.temperatureC() != null
            && input.temperatureC().compareTo(stored.temperatureC()) == 0
            && Objects.equals(input.occurredAt(), stored.occurredAt());
    }

    private static void validate(IncomingTelemetry input) {
        if (input == null
                || input.tenantId() == null
                || !input.tenantId().matches("[A-Za-z0-9_-]{1,64}")
                || input.eventId() == null
                || !input.eventId().matches("[A-Za-z0-9_-]{1,128}")
                || input.deviceId() == null
                || input.deviceId().isBlank()
                || input.sequence() < 0
                || input.temperatureC() == null
                || input.occurredAt() == null) {
            throw new IllegalArgumentException(
                "Invalid incoming telemetry");
        }
    }
}
~~~

**Important code explanation:**

1. `mongo.insert(...)` is used because the inbox stores **immutable** events; avoid `save`, which could overwrite state.
2. ID is `tenantId|eventId`, preserved across retries. The regex here prevents `|` characters from causing ambiguity; production must validate all inputs and tenant authorization.
3. `DuplicateKeyException` is **not retried**. The service reads back the record by stable ID.
4. Only when **all business fields match** does it return `ALREADY_ACCEPTED`.
5. `status`/`receivedAt` are excluded from comparison because they are per-attempt processing metadata.
6. If `existing` is null despite E11000, suspect **another index**, wrong ID, or read consistency; treat as a conflict requiring investigation.
7. If the record shares the ID with differing payload, throw `IngestConflictException` rather than swallowing the error.
8. `temperatureC.compareTo(...)` compares numeric values; if the business requires exact scale preservation (e.g., `26.50` vs. `26.5`), normalize to a canonical domain format consistently during serialization.
9. MongoDB readback here must use primary/consistent read settings; if configured to read from a lagging secondary, E11000 can occur before readback sees the record. See the retry ambiguity section.

**Design note:** the service returns `ALREADY_ACCEPTED` when the record exists and matches, even if `status=RECEIVED`/`PROCESSING`. That only means **durably stored in the inbox**, not that downstream has finished processing. If an API requires `ALREADY_PROCESSED`, inspect `DONE` state and target side effects.

## 8. Race Between Two Workers: The Unique Index Arbitrates

Two workers read `evt-1001` concurrently before the database has the record:

~~~mermaid
sequenceDiagram
    participant A as Instance A
    participant B as Instance B
    participant D as MongoDB
    A->>D: insert(_id=tenant-a|evt-1001)
    B->>D: insert(_id=tenant-a|evt-1001)
    D-->>A: Inserted
    D-->>B: E11000
    B->>D: findById(tenant-a|evt-1001)
    D-->>B: matching canonical event
    Note over A,B: Only one inbox document is created
~~~

This provides **atomic uniqueness at the MongoDB index**, not a distributed mutex across the entire business pipeline. Instance A could insert and crash before publishing to Kafka; Instance B returns `ALREADY_ACCEPTED` and **does not** immediately re-publish. Thus you still need **workers reading `PENDING` inbox entries with retries/leases**, or a transactional outbox tied to business mutations.

### 8.1. Why exists() Before insert Does Not Prevent Races

~~~java
// Broken if relied on as the sole deduplication guard.
if (!mongo.exists(queryByEventId, InboxEvent.class)) {
    mongo.insert(candidate, "event_inbox");
}
~~~

Between `exists` and `insert`, another worker can insert. **Unique index + catch/compare** is the authoritative guard. Pre-checks can optimize certain read-heavy workloads, yet never replace the constraint.

### 8.2. Never Use Spring Message ID as Event ID

Spring Integration generates a new `MessageHeaders.ID` whenever an event is wrapped or re-sent across flows. Using `message.getHeaders().getId()` as the unique key causes redeliveries to become distinct records. Use a stable business event ID preserved from source/ingress.

### 8.3. Duplicate Key Is for Detection, Not Cleanup

Never delete an existing document after E11000 just to retry the insert: doing so can wipe an already-processed event or another worker's record. If business rules allow amending a previously sent event, design a **new correction event with a distinct ID** or a conditional versioned update flow.

## 9. Retry Decision Table: Which Errors Should Be Retried?

**Never write `catch(Exception) { retry(); }` around MongoDB.** Blind retries can loop forever on configuration/bad-data errors or trigger extra side effects when prior outcomes were unknown.

| Error type | Java/driver example | Default decision | Reason |
|---|---|---|---|
| Unique constraint | `DuplicateKeyException` / code 11000 | **Do not blindly retry insert**; read back and classify | The constraint will not vanish on its own |
| Duplicate with matching payload | Record exists with identical business fields | `ALREADY_ACCEPTED` | Idempotent repeat |
| Duplicate with different payload | Same ID, differing business data | `CONFLICT`, quarantine / HTTP 409 | Requires source or business resolution |
| Schema/validation | `IllegalArgumentException`, mapping error | Never auto-retry | Data will not fix itself |
| Authentication/authorization | Mongo auth/permission denied | Never retry continuously | Fix credentials/roles |
| Temporarily unavailable | Failover, server selection, transient network | **Bounded** retry if safe | System can recover |
| Lock/write conflict | Transient conflict per MongoDB semantics | Policy-bounded operation/tx retry | State contention |
| Write concern timeout | `wtimeout`/missing majority ACK | **`UNKNOWN`**, reconcile with same ID | Write may already be applied |
| Network timeout after write | Socket timeout/lost response | **`UNKNOWN`**, keep same ID and reconcile | No proof write didn't happen |
| Transaction commit unknown | `UnknownTransactionCommitResult` | Retry **commit**/reconcile per protocol | Transaction may have committed |
| Retryable transient transaction | `TransientTransactionError` | Retry whole transaction if safe | Transaction can be re-executed |
| Database full/quota | Write errors/resource exhaustion | Alert/remediate before heavy retries | Blind retries worsen overload |
| Downstream Kafka/HTTP timeout | Publish result unknown | Reconcile broker/target using event ID | Not a MongoDB insert failure |

### 9.1. Three Retry Principles

1. **Classify errors accurately.** Spring Data exception translation helps, yet driver errors may be wrapped inside `MessagingException` or framework exceptions.
2. **Retry only idempotent operations or those with reconciliation.** If side effects cannot repeat safely, never auto-retry when outcomes are unknown.
3. **Enforce a retry budget.** Max attempts, backoff + jitter, deadlines, circuit breakers, DLQ/recovery, and monitoring.

### 9.2. TransientDataAccessException Does Not Cover All Network Errors

Spring Data has multiple `DataAccessException` branches: some resource/connection failures translate differently or surface as raw MongoDB driver exceptions. Configuring retries solely on `TransientDataAccessException` is a **conservative subset**, not an exhaustive classifier for all transient errors.

Never use `DataAccessException.class` as a retryable catch-all; it includes `DuplicateKeyException`, `DataIntegrityViolationException`, and other permanent errors. Write an explicit exception classifier tailored to your driver/Spring Data version and test the cause chain.

### 9.3. Retries Cannot Replace Business Reconciliation

When MongoDB wrote successfully but the response timed out, a retried `insert` with the same ID returns E11000. **Do not turn E11000 into an immediate permanent failure** if the app inspects matching records as already accepted; equally, never treat all E11000 errors as automatic successes.

## 10. Driver Retryable Writes Differ from Application Retries

The MongoDB Java driver supports **Retryable Writes** for eligible write operations when topology and write concern meet prerequisites. In modern drivers, this is usually enabled by default on replica sets and sharded clusters.

Example test URI:

~~~text
mongodb://mongo-test:27017/integration_lab?replicaSet=rs0&retryWrites=true&w=majority
~~~

This URI is illustrative; the replica set must exist with that exact name. Never set `retryWrites=true` on a standalone instance expecting identical behavior.

### 10.1. What Does the Driver Do?

When an eligible retryable write encounters a network error or cannot locate a healthy primary, the driver can **retry once** per MongoDB protocol using logical session/transaction numbers. This operates at the **driver/server layer**, distinct from Spring Integration re-invoking a business service.

| Mechanism | Who controls it? | What repeats? | Key takeaway |
|---|---|---|---|
| **Driver retryable write** | MongoDB driver | One eligible write operation per protocol | Typically retries once; requires topology/ACK support |
| **Spring Retry** | `RetryTemplate` / advice | Method/message handler | Can re-run the entire business handler |
| **Broker redelivery** | Kafka/JMS/AMQP container | Source message | Can occur after a process crash |
| **HTTP client retry** | Client/proxy | Entire API request | Needs `Idempotency-Key` |
| **Mongo transaction retry** | Driver/API/app | Transaction body or commit per error label | Do not confuse retrying whole tx with retrying commit |

**A single event can traverse all five retry layers.** If every layer retries blindly without a shared budget, attempts multiply into a retry storm.

### 10.2. Driver Retryable Writes Do Not Retry Every Error

- **`w:0` unacknowledged writes** are excluded from the retryable writes protocol.
- Standalone deployments do not support the same mechanism as replica sets/sharded clusters.
- Writes **inside a multi-document transaction** are not retried individually like outside-transaction writes.
- **Transaction commit/abort** has its own retry semantics; the driver may retry commit/abort even when `retryWrites=false`.
- **E11000 duplicate key** is not a transient connection failure just because its name contains "key"; it signals a unique constraint violation.

Starting in MongoDB **6.1**, the `NoWritesPerformed` error label helps identify cases where both attempts of a retryable write failed and **no writes were performed**. If this label is absent, **do not infer the opposite (that a write occurred)**; it only means the label does not prove zero writes. Reconcile by business key whenever outcomes remain unclear.

### 10.3. If Driver Retry Exists, Is Spring Retry Still Needed?

Potentially yes, serving a different layer. For example:

- The driver retries once during a brief primary failover.
- Spring Retry performs a few backed-off attempts when the service receives translated transient exceptions.
- The broker redelivers after a restart if the message was unacked.

All layers must preserve **the same business event ID**, identical idempotency semantics, and a combined time budget. In low-latency request paths, **avoid** long synchronous retries on the request thread; offload to durable queues/scheduled retries.

## 11. Spring Integration RequestHandlerRetryAdvice

Spring Integration provides `org.springframework.integration.handler.advice.RequestHandlerRetryAdvice`, wrapping a **`MessageHandler`** to retry when the handler throws an exception.

In Spring Integration 6.x, the advice uses `RetryTemplate` from `spring-retry`.

### 11.1. RetryAdvice Bean Retrying Only Transient Errors

~~~java
package example.mongoingest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import org.springframework.dao.TransientDataAccessException;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.support.RetryTemplate;

@Configuration
public class MongoRetryAdviceConfig {

    @Bean("mongoTransientRetryAdvice")
    public RequestHandlerRetryAdvice mongoTransientRetryAdvice() {

        RetryTemplate template = RetryTemplate.builder()
            .maxAttempts(3)
            .exponentialBackoff(200L, 2.0, 2000L, true)
            .retryOn(TransientDataAccessException.class)
            .traversingCauses()
            .build();

        RequestHandlerRetryAdvice advice =
                new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(template);
        // No RecoveryCallback set here:
        // after 3 attempts the exception propagates to the source.
        return advice;
    }
}
~~~

**Explanation:**

- `maxAttempts(3)` = **1 initial attempt + up to 2 retries**, not 3 retries after the initial attempt.
- Backoff includes jitter to reduce thundering herds hitting MongoDB simultaneously.
- `retryOn(TransientDataAccessException.class)` is a **conservative** classifier and does not cover every MongoDB driver error.
- `traversingCauses()` is critical because Spring Integration often wraps underlying errors inside `MessagingException`.
- `DuplicateKeyException` is **not** retried under this policy because it is not a subclass of the chosen transient hierarchy.
- Without a `RecoveryCallback`, after exhausting attempts the exception propagates upstream or to the configured error channel.
- This stateless advice holds the calling thread across backoff sleeps; under high traffic and long backoffs, prefer off-thread scheduled retries over blocking more consumer threads.

### 11.2. Service Activator Wrapped with Advice

~~~java
package example.mongoingest;

import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class MongoInboxEndpoint {

    private final MongoInboxIngestService service;

    public MongoInboxEndpoint(MongoInboxIngestService service) {
        this.service = service;
    }

    @ServiceActivator(
        inputChannel = "mongoIngestRequests",
        adviceChain = "mongoTransientRetryAdvice")
    public IngestOutcome handle(IncomingTelemetry input) {
        return service.ingest(input);
    }
}
~~~

Within the same Spring context, `MongoInboxIngestService` returns `INSERTED`/`ALREADY_ACCEPTED` or throws conflict/exceptions. The advice retries only configured transient errors **when invoking the handler**.

**Do not slap retry advice indiscriminately onto every downstream handler**: if a handler already published to Kafka and then threw while logging/committing, retrying the whole handler publishes to Kafka multiple times.

### 11.3. @MessagingGateway for Synchronous Request/Reply

~~~java
package example.mongoingest;

import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway
public interface MongoInboxGateway {

    @Gateway(
        requestChannel = "mongoIngestRequests",
        replyTimeout = 5000)
    IngestOutcome ingest(IncomingTelemetry event);
}
~~~

Register the gateway interface via `@IntegrationComponentScan` or equivalent configuration. Calling:

~~~java
IngestOutcome outcome = gateway.ingest(event);
~~~

returns the service outcome via request/reply **provided the flow stays synchronous and does not cross an async channel**. `replyTimeout` caps how long the caller waits for a reply; it does not roll back a MongoDB write. If the caller times out after the DB wrote, retrying with the same event ID leads to duplicate detection.

### 11.4. Using RetryAdvice with the Java DSL

Instead of `@ServiceActivator`, an `IntegrationFlow` can use:

~~~java
@Bean
public IntegrationFlow mongoIngestFlow(
        MongoInboxIngestService service,
        RequestHandlerRetryAdvice mongoTransientRetryAdvice) {

    return IntegrationFlow.from("mongoIngestRequests")
        .handle(service, "ingest",
            endpoint -> endpoint.advice(
                mongoTransientRetryAdvice))
        .get();
}
~~~

**This is an alternative** to the annotation endpoint in section 11.2. Never register both consumers on `mongoIngestRequests` expecting messages to follow one predictable path. In Java DSL, ref/method resolution and reply channels follow Spring Integration's message handler contract.

## 12. Recovery Channels, Error Channels, and ACKs

Once retries are exhausted:

- **No `RecoveryCallback`:** the exception propagates to the caller or error flow per channel/endpoint. For JMS/Kafka, the container decides rollback/redelivery based on the error and config.
- **With `RecoveryCallback` sending an `ErrorMessage`:** the error is routed to the recovery channel; depending on the callback, the error is **considered handled** and stops propagating.
- **With a confirmed durable DLQ/quarantine:** you may decide to ACK the source after durably persisting the failed record per business policy.
- **Merely logging and returning:** unacceptable when data cannot be lost.

### 12.1. ErrorMessageSendingRecoverer

Spring Integration supports:

~~~java
import org.springframework.integration.handler.advice.ErrorMessageSendingRecoverer;

RequestHandlerRetryAdvice advice =
        new RequestHandlerRetryAdvice();

advice.setRetryTemplate(retryTemplate);
advice.setRecoveryCallback(
        new ErrorMessageSendingRecoverer(
            recoveryMessageChannel));
~~~

This is a fragment assuming `retryTemplate`/`recoveryMessageChannel` are injected/initialized. **Critical consequence:** once the recovery callback sends the error to the channel and returns normally, upstream may treat the handler as having succeeded. If `recoveryMessageChannel` is an in-memory `QueueChannel` or a logger-only handler, **there is no durability guarantee** to safely ACK the source.

If events must never be lost:

1. The recovery channel consumer must persist retries/dead-letters durably (or keep propagating errors so the broker redelivers).
2. Define a fallback if the recovery channel fills up or fails.
3. Never write raw sensitive payloads to unauthorized logs/DLQs.
4. ACK the original source only after durable recovery persistence is confirmed.
5. Guard against error-channel loops (an error handler failing back onto the same error channel).

### 12.2. XML Retry Advice

Spring Integration XML (6.x-compatible pattern):

~~~xml
<int:service-activator
        input-channel="mongoIngestRequests"
        ref="mongoInboxEndpoint"
        method="handle">
    <int:request-handler-advice-chain>
        <ref bean="mongoTransientRetryAdvice"/>
    </int:request-handler-advice-chain>
</int:service-activator>
~~~

This configuration is **an alternative to the annotated endpoint**; `mongoInboxEndpoint` and `mongoTransientRetryAdvice` beans must exist. Declare version-matching `int` XML namespaces/schemas and channels. Referencing the Java advice bean preserves the `RetryTemplate` **exception classifier**; never attach a default catch-all XML retry advice expecting `DuplicateKeyException` to be skipped.

### 12.3. An Error Channel Is Not a Broker Dead-Letter Queue

An `ErrorMessage` on `errorChannel` is a **Spring Message wrapping an exception**, not a guarantee the broker dead-lettered the message. To avoid data loss, the recovery flow must include durable persistence/ACK handling.

If the error consumer itself throws, trace where that exception propagates to prevent infinite loops or premature upstream ACKs.

## 13. Stateful Retry and Broker Redelivery

Spring Integration distinguishes:

- **Stateless retry:** retries immediately within the same handler invocation, holding the call stack/thread across attempts.
- **Stateful retry:** tracks retry state by a **stable key**, rethrows the exception so **the source** (JMS/Kafka/AMQP...) redelivers, continuing the attempt counter/backoff on the next delivery.

### 13.1. Why Stateful Retry Is Useful

Suppose a JMS listener receives an order event. If the DB fails over and processing must retry, rolling back the JMS transaction lets the broker redeliver later instead of holding a thread asleep inside the MongoDB handler.

However:

- The stable state key must derive from the source's stable business event ID/message identity, never a fresh Spring Message UUID.
- Spring Integration 6.x and 7.x differ in stateful retry configuration APIs; check your version's Javadocs.
- Stateful retry caches are bounded and typically in-memory; they do not magically create durable exactly-once semantics.
- Coordinate broker redelivery policies, max delivery counts, and dead-letter queues with retry state.
- Avoid multiplying attempts infinitely by stacking long retry advice, unlimited broker redeliveries, and unlimited HTTP client retries.

### 13.2. A Sensible Layered Plan

~~~text
MongoDB driver retry (driver level, eligible operations)
        ↓
Spring Integration handler retry (2–3 attempts, transient only)
        ↓
Exception propagates if still failing
        ↓
Broker nack/rollback → delayed/backed-off redelivery + DLQ
        ↓
Durable retry/quarantine & operational reconciliation
~~~

Allocate a **time budget**. An HTTP API with a 3-second deadline cannot afford 3 attempts × 2 seconds plus MongoDB driver server selection delays. Under heavy traffic, prefer durable async retries over stretching request latency.

## 14. Retrying a Transaction Differs from Retrying a Single Insert

Inside a multi-document MongoDB transaction:

- All operations must share the same `ClientSession`/transaction context.
- Write concern applies at the **transaction level**, not per individual insert.
- Errors before commit can abort the transaction.
- Commit responses may be ambiguous; never blindly replay external side effects.
- MongoDB attaches error labels such as `TransientTransactionError` and `UnknownTransactionCommitResult`.
- MongoDB 8.1+: **upsert duplicate-key errors inside a transaction are not automatically retried by the server** per documented behavior.

### 14.1. A Transaction Writing Event + Outbox

~~~java
@Service
public class OrderEventApplicationService {

    private final MongoOperations mongo;

    public OrderEventApplicationService(MongoOperations mongo) {
        this.mongo = mongo;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void appendOrderAndOutbox(
            OrderRecord order, OutboxEvent outbox) {

        mongo.insert(order, "orders");
        mongo.insert(outbox, "outbox_events");
        // Never publish to Kafka before the transaction commits.
    }
}
~~~

This is a **fragment** requiring `OrderRecord`, `OutboxEvent`, and a `MongoTransactionManager` bean sharing the same `MongoDatabaseFactory`. Transactions require a supporting MongoDB topology (typically a replica set). A `DuplicateKeyException` from an insert aborts/fails the transaction; never catch it and keep using the failed transaction session to retry an insert.

### 14.2. Unknown Commit Result

~~~mermaid
sequenceDiagram
    participant I as Integration service
    participant M as MongoDB
    I->>M: insert order + outbox in txn
    I->>M: commitTransaction()
    M->>M: commit completes
    M--xI: commit ACK lost
    Note over I: UnknownTransactionCommitResult
    I->>M: retry commit per driver protocol / reconcile business keys
~~~

When the commit outcome is unknown, **never re-invoke external side effects outside MongoDB** like sending emails/Kafka inside a transaction callback. Follow the driver's transaction retry protocol, then read back state by business keys and inspect the outbox. When an operation inside a transaction hits a transient error before commit, retrying the entire transaction is safe only if the transaction body **has no external non-DB side effects**.

### 14.3. Nesting @Transactional and RetryAdvice

Where advice/transactions wrap determines whether an attempt gets a fresh session or runs inside an existing transaction. For example:

- Retry **outside** the transactional service: each attempt opens a fresh transaction.
- Retry **inside** the transaction: an error may mark the transaction rollback-only; retrying one insert inside the same session will not yield a clean transaction.
- An async `QueueChannel` switches threads, so an imperative transaction context does not propagate to the worker.
- Self-invocation `this.method()` bypasses Spring AOP `@Transactional`.

Run real integration tests to verify **attempt boundaries** and commit/abort behavior. Never assume stacking `@Retryable` + `@Transactional` + Integration `RetryAdvice` is automatically safe.

## 15. Reactive MongoDB: onErrorResume, retryWhen, and Duplicate Comparison

With `ReactiveMongoOperations`, errors occur inside the publisher **upon subscription**, not necessarily when invoking the method constructing the `Mono`.

### 15.1. Retry Only Transient Errors, Never Duplicates

~~~java
package example.mongoingest;

import java.time.Duration;

import org.springframework.dao.TransientDataAccessException;
import org.springframework.data.mongodb.core.ReactiveMongoOperations;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public final class ReactiveInboxWriter {

    private final ReactiveMongoOperations mongo;

    public ReactiveInboxWriter(ReactiveMongoOperations mongo) {
        this.mongo = mongo;
    }

    public Mono<InboxEvent> insertWithTransientRetry(
            InboxEvent event) {

        return mongo.insert(event, "event_inbox")
            .retryWhen(
                Retry.backoff(2, Duration.ofMillis(200))
                    .maxBackoff(Duration.ofSeconds(2))
                    .filter(error ->
                        error instanceof TransientDataAccessException));
    }
}
~~~

**`Retry.backoff(2, ...)` allows 2 retries after the initial subscription**, differing from Spring Retry's `maxAttempts(3)` phrasing. This pattern is also a **conservative classifier** that should be expanded for appropriate driver failures after testing. `DuplicateKeyException` is not retried.

### 15.2. Classifying Duplicates in a Reactive Chain

~~~java
public Mono<IngestOutcome> insertOrRecognize(
        IncomingTelemetry input) {

    validate(input); // Reuse synchronous service validation.

    InboxEvent candidate = buildCandidate(input);

    return mongo.insert(candidate, "event_inbox")
        .thenReturn(IngestOutcome.INSERTED)
        .onErrorResume(
            DuplicateKeyException.class,
            duplicate -> mongo.findById(
                    candidate.id(),
                    InboxEvent.class,
                    "event_inbox")
                .flatMap(existing -> {
                    if (sameBusinessEvent(input, existing)) {
                        return Mono.just(
                            IngestOutcome.ALREADY_ACCEPTED);
                    }
                    return Mono.error(new IngestConflictException(
                        "Event identity/content conflict",
                        duplicate));
                })
                .switchIfEmpty(
                    Mono.error(new IngestConflictException(
                        "Duplicate key on another index or unseen record",
                        duplicate))));
}
~~~

This is a **fragment** of `ReactiveInboxWriter` needing imports for `DuplicateKeyException`, `Mono`, and definitions of `validate`/`buildCandidate`/`sameBusinessEvent` matching the sync service in section 7. To preserve consistency, never use unvalidated raw DTOs or secondary-lagging read preferences when reconciling.

### 15.3. Never Swallow onError

~~~java
// Wrong if business requires durable persistence:
return mongo.insert(event)
    .onErrorResume(e -> Mono.empty())
    .then();
~~~

Any network/DB error turns into `onComplete`, causing upstream to ACK erroneously. Any fallback must persist durably to a retry/dead-letter store or propagate the error.

### 15.4. Mono Retry Differs from Transaction Retry

When a `Mono` runs inside `TransactionalOperator`, the relative order of `retryWhen` and `as(tx::transactional)` decides whether **the whole transaction** retries or just one operation inside the same transaction. Never place `retryWhen` haphazardly inside an already-failed transaction.

With `ReactiveMongoTransactionManager`, operations in the same transaction must compose sequentially per driver rules; never run concurrent `flatMap` operations on the same session.

## 16. Bulk Inserts: Partial Success and Per-Index Duplicates

MongoDB bulk/`insertMany` handles multiple documents in one operation. When a record violates a unique key:

- **Ordered bulk** stops at the first error in sequence; earlier documents may have been written.
- **Unordered bulk** continues processing other operations where possible; ordering is not guaranteed.
- Unless wrapped in a transaction, an exception **does not** automatically roll back already-inserted documents.
- `MongoBulkWriteException` carries a list of write errors with operation indexes, code `11000`, and completed write results.
- Never catch a bulk exception and retry **the entire batch with new IDs**.
- If retrying the batch with the same business IDs, already-written records will produce further E11000s; reconcile **per item**.

### 16.1. mongosh Demo

~~~javascript
use integration_lab

db.bulk_events.insertMany(
  [
    { _id: "evt-a", status: "NEW" },
    { _id: "evt-a", status: "NEW" },
    { _id: "evt-b", status: "NEW" }
  ],
  { ordered: false }
)
// E11000 occurs on the second element, yet evt-a and evt-b
// may already have been inserted successfully.
~~~

Do not assume error indexes imply commit ordering across shards. For large workloads, track **per-`eventId` results** or an inbox status for reconciliation.

### 16.2. Never Apply One Blanket Retry Policy to a Bulk Batch

An `insertMany` of 1,000 events represents 1,000 business units. An error on document #17 should not fail the other 999 events. Design retries/ACKs per **business unit**, not just "HTTP batch succeeded/failed".

## 17. MongoDbStoringMessageHandler Does Not Automatically "Ignore Duplicates"

The Spring Integration MongoDB outbound channel adapter uses `MongoDbStoringMessageHandler` to write payloads into a collection via `MongoOperations`. Normally it uses `save` semantics, not **insert-only + catch E11000 + payload comparison**.

### 17.1. Simple Java DSL Writer

~~~java
package example.mongoingest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mongodb.dsl.MongoDb;
import org.springframework.data.mongodb.core.MongoOperations;

@Configuration
@EnableIntegration
public class MongoRawWriterConfig {

    @Bean
    public IntegrationFlow rawMongoWriter(MongoOperations mongo) {
        return IntegrationFlow.from("mongoRawWrites")
            .handle(
                MongoDb.outboundChannelAdapter(mongo)
                    .collectionName("event_inbox"))
            .get();
    }
}
~~~

**This is a demo flow**, not a replacement for `MongoInboxIngestService` when business logic requires insert-only and `INSERTED` / `ALREADY_ACCEPTED` / `CONFLICT` classification. Repeated source files or HTTP requests can cause `save` to overwrite existing documents. For specific write concerns, configure `MongoTemplate`/driver; `MessageChannel` has no write concern property of its own.

### 17.2. When to Use a Service Instead of the Storing Adapter

When the business must classify E11000:

1. Producer sends `Message<IncomingTelemetry>` to the endpoint.
2. Endpoint validates/authorizes and calls `MongoInboxIngestService.ingest(...)`.
3. Service uses `insert` + unique constraint + record comparison after `DuplicateKeyException`.
4. Service returns an explicit outcome or throws conflict.
5. Retry advice retries only classified transient failures.
6. Source ACK relies on the **durable outcome**, not merely channel acceptance.

`MongoDbOutboundGateway` is suited for **request/reply queries**, not insert-only writing. You can use a gateway for readback, though a separate gateway call does not automatically share a MongoDB session/transaction with a preceding write.

## 18. MongoDbMessageSource Polling and Duplicates

The Spring Integration MongoDB inbound adapter uses `MongoDbMessageSource`, called on schedule by a poller via `receive()`.

~~~mermaid
flowchart LR
    P["Poller"] --> M["MongoDbMessageSource"]
    M --> Q["find(status=NEW, limit=50)"]
    Q --> L["Message<List<InboxEvent>>"]
    L --> S["Splitter"]
    S --> H["Business handler"]
    H --> D["Kafka / HTTP / DB"]
~~~

Under default blocking configuration with `expectSingleResult(false)`, the source emits **one `Message<List<T>>`**. It does not remember polled documents or automatically mark them `DONE`.

### 18.1. Query Limit and Poller Limit Differ

~~~text
fixedDelay(5000)
maxMessagesPerPoll(1)
Query.limit(50)
~~~

This caps **one source receive per poll** and **at most 50 MongoDB documents per query**; it does not make the next poll automatically select 50 new documents. If the query still targets `status=NEW`, the same events can be re-read.

### 18.2. updateExpression Does Not Prove Business Processing Finished

~~~java
MongoDb.inboundChannelAdapter(
        mongo,
        "{ 'status': 'NEW' }")
    .collectionName("event_inbox")
    .entityClass(InboxEvent.class)
    .update(new Update().set("status", "CLAIMED"));
~~~

This is a builder fragment to wire into an `IntegrationFlow` with a poller. If two workers query `NEW` before the update, both can still read the same document. If the app crashes after `CLAIMED` before publishing to Kafka, events get stuck. **`CLAIMED` is not `DONE`**; you still need owner/lease/attempts, recovery, and idempotent downstreams.

### 18.3. Unique Insert and Atomic Claim Are Two Different Problems

- **Unique inbox insert:** prevents creating two records for the same business event ID.
- **Atomic work claim:** ensures only one worker owns a work item at a time, typically via conditional `findAndModify`.
- **Idempotent downstream:** prevents duplicate business side effects even on post-crash redeliveries.
- **Durable outbox:** persists outbound publish intent instead of relying on process memory.

## 19. ACK Policy by Data Source

| Source | When to ACK if inbox durability is required? | What to do on failure? |
|---|---|---|
| HTTP API | After MongoDB insert/reconciliation confirms | Client retries with the same `Idempotency-Key` |
| Kafka consumer | After durable processing per contract | Container retry/seek/DLT without committing offset |
| JMS queue | After durable business state/transaction | Roll back session / nack when DB fails |
| AMQP/RabbitMQ | After durable state | Bounded nack/requeue, DLX per policy |
| File inbound | After parsing/writing durable inbox | Quarantine/move by status; never delete files early |
| SFTP inbound | After downloading and persisting content/recoverable markers | Retry transfer/handler; avoid losing work to early `seen` filters |
| MongoDB polling | After claim/business state per contract | Retries, lease expiry, owner/version checks |

**This table states architectural principles**, not identical ACK APIs across all adapters. Check your version's Kafka/JMS/AMQP/file/SFTP adapter traits, transaction threading, error channels, and recovery handlers.

### 19.1. HTTP Idempotency-Key

~~~text
POST /telemetry
Idempotency-Key: evt-1001

Body: { "tenantId":"tenant-a", "eventId":"evt-1001", ... }
~~~

The server authenticates the tenant and binds the key to the canonical request body. Same key + same business payload returns the equivalent outcome; same key + different payload returns HTTP 409/conflict. Never trust a client-supplied header without authorization checks.

### 19.2. Kafka/JMS and the ACK Gap

If a consumer commits its Kafka offset or JMS ACK **before** the MongoDB inbox write finishes, a crash loses the event. If it ACKs **after**, a crash between MongoDB ACK and broker ACK causes redelivery, where the unique ID makes ingestion idempotent.

A `@Transactional("mongoTransactionManager")` manages only the MongoDB session; **it does not commit JMS/Kafka transactions**. Kafka producer idempotence also does not replace end-to-end business idempotency across MongoDB.

### 19.3. File/SFTP/UDP Differ from Brokers

File/SFTP rely on remote/local filters, file moves/renames, and source state; they lack default broker ACK semantics. UDP is best-effort with no broker redelivery. Implement replay/recovery per source contract rather than expecting a unique MongoDB index to make the source re-send lost data.

## 20. Transactional Outbox and Target Duplicates

A reliable pipeline can use a MongoDB transaction to write **business state + outbox event**:

~~~mermaid
sequenceDiagram
    participant P as Source
    participant I as Ingest
    participant DB as MongoDB
    participant W as Outbox worker
    participant B as Broker
    participant C as Consumer
    P->>I: evt-1001
    I->>DB: transaction insert inbox + outbox
    DB-->>I: commit ACK
    I-->>P: accepted
    W->>DB: atomic claim eventId
    W->>B: publish eventId
    B-->>W: broker ACK
    W->>DB: conditional mark SENT
    B->>C: eventId
    C->>C: unique dedup + business effect
~~~

### 20.1. Why Can an Outbox Still Publish Duplicates?

The outbox worker can publish successfully and crash **before marking `SENT`**. Once the lease expires, another worker re-publishes. Thus an outbox usually provides **at-least-once delivery**, and consumers must deduplicate by the same event ID or be idempotent.

### 20.2. Unique Keys Do Not Replace Transactions

A unique inbox key prevents two records for one event; it **does not make two inserts (inbox + outbox) atomic**. When two collections must commit/abort together, use `MongoTransactionManager` on the same `MongoDatabaseFactory` in a transaction-capable deployment. MongoDB transactions still **do not commit Kafka/JMS/HTTP**.

### 20.3. Payload Conflict Errors in the Outbox

If an old event ID is reused with new content, that is a business conflict, not a harmless duplicate to ignore. Use a separate correction event ID/version or a controlled business update workflow; never drop unique constraints to "silence errors".

## 21. Unit Testing: Matching Payloads, Differing Payloads, and Retry Policies

### 21.1. Testing INSERTED and ALREADY_ACCEPTED

~~~java
package example.mongoingest;

import java.math.BigDecimal;
import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.MongoOperations;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class MongoInboxIngestServiceTest {

    private IncomingTelemetry event() {
        return new IncomingTelemetry(
            "tenant-a", "evt-1001", "node-7", 1001L,
            new BigDecimal("26.5"),
            Instant.parse("2026-11-23T02:00:00Z"));
    }

    @Test
    void firstInsertReturnsInserted() {
        MongoOperations mongo = mock(MongoOperations.class);
        MongoInboxIngestService service =
                new MongoInboxIngestService(mongo);

        assertEquals(IngestOutcome.INSERTED,
                service.ingest(event()));

        verify(mongo).insert(
            any(InboxEvent.class), eq("event_inbox"));
    }

    @Test
    void sameEventAfterDuplicateIsAlreadyAccepted() {
        MongoOperations mongo = mock(MongoOperations.class);
        MongoInboxIngestService service =
                new MongoInboxIngestService(mongo);

        doThrow(new DuplicateKeyException("E11000"))
            .when(mongo)
            .insert(any(InboxEvent.class), eq("event_inbox"));

        InboxEvent existing = new InboxEvent(
            "tenant-a|evt-1001",
            "tenant-a", "evt-1001", "node-7", 1001L,
            new BigDecimal("26.50"),
            Instant.parse("2026-11-23T02:00:00Z"),
            "DONE", Instant.parse("2026-11-23T02:01:00Z"));

        when(mongo.findById(
            eq("tenant-a|evt-1001"),
            eq(InboxEvent.class),
            eq("event_inbox")))
            .thenReturn(existing);

        assertEquals(IngestOutcome.ALREADY_ACCEPTED,
                service.ingest(event()));
    }

    @Test
    void differentPayloadIsConflict() {
        MongoOperations mongo = mock(MongoOperations.class);
        MongoInboxIngestService service =
                new MongoInboxIngestService(mongo);

        doThrow(new DuplicateKeyException("E11000"))
            .when(mongo)
            .insert(any(InboxEvent.class), eq("event_inbox"));

        InboxEvent existing = new InboxEvent(
            "tenant-a|evt-1001",
            "tenant-a", "evt-1001", "node-7", 1001L,
            new BigDecimal("99.0"),
            Instant.parse("2026-11-23T02:00:00Z"),
            "RECEIVED", Instant.now());

        when(mongo.findById(
            anyString(),
            eq(InboxEvent.class),
            eq("event_inbox")))
            .thenReturn(existing);

        assertThrows(IngestConflictException.class,
                () -> service.ingest(event()));
    }
}
~~~

These tests verify **business decision logic**, not that real MongoDB has unique indexes. Use a separate test database for real verification.

### 21.2. Testing That RetryTemplate Does Not Retry Duplicates

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.retry.support.RetryTemplate;
import static org.junit.jupiter.api.Assertions.*;

class RetryClassificationTest {

    @Test
    void duplicateKeyIsNotRetried() {
        RetryTemplate template = RetryTemplate.builder()
            .maxAttempts(3)
            .retryOn(
                org.springframework.dao.TransientDataAccessException.class)
            .traversingCauses()
            .build();

        AtomicInteger calls = new AtomicInteger();

        assertThrows(DuplicateKeyException.class,
            () -> template.execute(context -> {
                calls.incrementAndGet();
                throw new DuplicateKeyException("E11000");
            }));

        assertEquals(1, calls.get());
    }
}
~~~

Add tests throwing a `TransientDataAccessException`, verifying `maxAttempts=3` equals **1 initial + 2 retries**, and testing a `MessagingException` cause chain. Also test E11000 from another unique index where `findById` returns null, asserting it throws conflict rather than `ALREADY_ACCEPTED`.

## 22. Integration Testing Real MongoDB and Concurrent Inserts

### 22.1. Testing Duplicates Against a Test Database

Use an isolated test MongoDB instance or Testcontainers if Docker is available on the runner. Example `@SpringBootTest`:

~~~java
package example.mongoingest;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class MongoInboxIngestIT {

    @Autowired MongoOperations mongo;
    @Autowired MongoInboxIngestService service;

    @Test
    void duplicateIsIdempotentIfContentMatches() {
        String id = "it-" + UUID.randomUUID();

        IncomingTelemetry event = new IncomingTelemetry(
            "tenant-test", id, "node-test", 100L,
            new BigDecimal("26.5"),
            Instant.parse("2026-11-23T02:00:00Z"));

        String mongoId = "tenant-test|" + id;
        Query byId = Query.query(
                Criteria.where("_id").is(mongoId));

        try {
            assertEquals(IngestOutcome.INSERTED,
                    service.ingest(event));
            assertEquals(IngestOutcome.ALREADY_ACCEPTED,
                    service.ingest(event));
            assertEquals(1,
                mongo.count(byId, "event_inbox"));
        } finally {
            mongo.remove(byId, "event_inbox");
        }
    }
}
~~~

**Prerequisite:** the test context has the service bean, real `MongoOperations`, and the proper database/indexes; `@SpringBootTest` does not start a MongoDB server on its own. Clean up only test-created keys and never run tests against production.

### 22.2. Two Workers Inserting the Same Event Concurrently

In a real MongoDB integration test:

1. Generate a unique random event ID.
2. Have two threads/instances wait on a `CountDownLatch`, then call `ingest(event)`.
3. Assert **exactly one** returns `INSERTED` and the other returns `ALREADY_ACCEPTED` when payloads match.
4. Assert only one document exists for the unique key.
5. Repeat with the same ID but differing payloads between the two workers: the losing worker must report `CONFLICT`.
6. Clean up the exact test key and use finite timeouts on threads.
7. When testing two real app instances, point both at the same MongoDB deployment/collection/unique index.

Testing races with Mockito cannot prove MongoDB constraint enforcement. Testing two clients on one local MongoDB is only part of the picture; failover/replication consistency requires a dedicated test topology.

### 22.3. Testing Unknown Write Outcomes

On an isolated test replica set:

- Intentionally induce a network timeout/lost ACK after an insert.
- Reuse the exact same `_id`/business event ID on retry.
- When the retry hits E11000, query/read back the record and compare canonical fields.
- Never claim the first exception meant the write rolled back.
- Distinguish MongoDB's `NoWritesPerformed` error label when supported by your version/driver.
- If readback fails to see the record immediately due to secondary reads, inspect read preference/read concern before concluding conflict.
- Monitor retry counts across driver, Spring Retry, and broker to prevent retry storms.

**Never induce network faults or failovers on production** for practice.

## 23. Reactive Testing with StepVerifier

Reactive MongoDB emits errors through the publisher upon subscription. Example against a test collection:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.ReactiveMongoOperations;
import reactor.test.StepVerifier;

@SpringBootTest
class ReactiveDuplicateKeyIT {

    @Autowired ReactiveMongoOperations reactiveMongo;

    @Test
    void repeatedInsertEmitsDuplicateError() {
        InboxEvent event = testEventWithUniqueId();

        StepVerifier.create(
            reactiveMongo.insert(event, "event_inbox")
                .then(reactiveMongo.insert(
                    event, "event_inbox")))
            .expectError(DuplicateKeyException.class)
            .verify();
    }
}
~~~

This is a **test fragment**: supply `testEventWithUniqueId()`, the test collection/unique index, `reactor-test` dependency, and post-test cleanup including on error paths. Never run against production. To test the reactive service `insertOrRecognize(...)`, subscribe two invocations via `StepVerifier` and assert `INSERTED` then `ALREADY_ACCEPTED`.

### 23.1. Never retryWhen Every Throwable

~~~java
// Wrong: retries permanent duplicate errors too.
return reactiveMongo.insert(event, "event_inbox")
    .retryWhen(Retry.max(10));
~~~

Instead, retry only classified errors:

~~~java
return reactiveMongo.insert(event, "event_inbox")
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(200))
            .filter(ex ->
                ex instanceof TransientDataAccessException));
~~~

This fragment requires `Retry`, `Duration`, and `TransientDataAccessException` imports; it handles only a **subset** of transient errors. `onErrorResume(DuplicateKeyException.class, ...)` must **read back the record and verify business contents**, never returning `Mono.empty()` to mask all duplicates.

## 24. Metrics, Logging, and Production Alerts

Suggested metrics (do not assume the framework emits these exact names automatically):

| Metric | Meaning |
|---|---|
| `mongo_inbox_insert_attempt_total` | Insert attempt count |
| `mongo_inbox_inserted_total` | Acknowledged inserts |
| `mongo_duplicate_key_total` | Total E11000 errors |
| `mongo_duplicate_same_payload_total` | Idempotent repeats |
| `mongo_duplicate_conflict_total` | ID collisions with differing content / index conflicts |
| `mongo_application_retry_attempt_total` | Handler-level retries |
| `mongo_retry_exhausted_total` | Exhausted retry budgets |
| `mongo_unknown_write_outcome_total` | Timeouts/lost ACKs with indeterminate results |
| `mongo_reconciliation_success_total` | Successful business-key reconciliations |
| `mongo_reconciliation_unresolved_total` | Unresolved states |
| `mongo_bulk_partial_success_total` | Batches with partial successes |
| `mongo_inbox_pending_depth` | Events awaiting business handler |
| `mongo_outbox_redelivery_total` | Events re-sent by broker/worker |
| `mongo_business_committed_total` | Business side effects committed |
| `integration_dlq_depth` | Events in durable dead-letter/quarantine |

Useful logs:

~~~text
ingest_attempt       eventId=evt-1001 tenant=tenant-a
mongo_insert_ack     eventId=evt-1001
mongo_duplicate      eventId=evt-1001 index=_id_
reconciliation_ok    eventId=evt-1001 outcome=ALREADY_ACCEPTED
business_conflict    eventId=evt-1001 reason=payload_mismatch
retry_exhausted      eventId=evt-1001 attempts=3
~~~

**Never log sensitive payloads, credentials, or full URIs containing passwords.** Never attach per-`eventId`/per-`deviceId` high-cardinality metric labels; correlation IDs can be managed in tracing/logs with proper retention and PII rules.

### 24.1. When Should Alerts Fire?

- `duplicate_same_payload` increases: may indicate source redeliveries or slow ACKs, not necessarily a bug.
- `duplicate_conflict` increases: indicates ID collisions, buggy producers, or broken data models/indexes.
- Retry attempts spike alongside MongoDB failover: check for retry storms, connection pool pressure, and backoff settings.
- Outbox/inbox backlog grows after downtime: check capacity and recovery.
- DLQ grows: requires a runbook, owner, and replay policy.
- Unknown outcomes rise: inspect write concerns, driver timeouts, and network health.

## 25. Troubleshooting Checklist

| Symptom | Likely cause | Action |
|---|---|---|
| E11000 on "first" request | Record already existed from earlier run or another index collided | Read by key; inspect index name |
| Repeated retries still hit E11000 | Permanent unique constraint violation | Stop retrying duplicates; reconcile |
| Same ID, different payload | Producer mis-reused a key | Quarantine/conflict; never overwrite |
| `save` succeeds silently yet state resets | Replaced document sharing ID | Use insert-only for immutable inboxes |
| Two workers both read absent | `exists → insert` race | Let unique index arbitrate |
| HTTP timeout yet record exists | Lost ACK | Retry with same `Idempotency-Key` |
| Kafka redelivery after DB commit | Uncommitted offset | Inbox idempotency and proper ACK order |
| MongoDB error after write yet document exists | Unknown outcome | Read back by ID |
| Error recovery ran yet message ACKed | Recoverer suppressed error | Durable recovery or propagate |
| `RetryAdvice` never triggers | Miswired endpoint/advice or different exception type | Inspect `adviceChain` and cause chain |
| Duplicates still retried | Default classifier retries all exceptions | Restrict `retryOn` to transient only |
| Rapid retries overload DB | Missing backoff/jitter | Cap attempts and add jittered backoff |
| Driver + Spring + broker multiply retries | Uncoordinated retry budgets | Align unified deadlines/caps |
| Bulk insert errors despite some docs saved | Partial success | Reconcile per event ID |
| Unique index deploy fails | Pre-existing duplicates/nulls | Controlled data migration |
| Sharded uniqueness misbehaves | Index incompatible with shard key | Review schema/shard key |
| Inbox stuck in `PROCESSING` | Worker crash / unexpiring lease | Lease expiry, recovery, fencing |
| Duplicate business effects at target | Missing idempotent consumer | Unique downstream inbox |
| Transaction aborts, then single insert retried | Transaction context already invalid | Retry at proper transaction boundary |
| Reactive `Mono` error swallowed | `onErrorResume` returning empty | Propagate or quarantine before ACK |
| Tests pass without catching payload conflicts | Missing differing-content test case | Add unit/integration conflict cases |

### 25.1. Isolation Sequence

~~~text
Source event + stable business key
    -> validate + tenant authorization
    -> Spring Integration Message / handler
    -> RetryAdvice (transient only)
    -> MongoOperations.insert + unique index
    -> E11000? findById + canonical comparison
    -> INSERTED / ALREADY_ACCEPTED / CONFLICT
    -> ACK source or durable retry/DLQ
    -> Inbox processor + atomic claim/lease
    -> Outbox + broker publish
    -> Idempotent business commit at target
~~~

`MessageChannel.send()==true` does not prove a DB commit when using asynchronous channels. Always align the **source ACK → durable state → business side effect** boundary.

## 26. Comprehensive Hands-On Lab

Build an **HTTP/Kafka/JMS → Spring Integration → MongoDB `event_inbox` → worker → Kafka/JMS/HTTP/DB** pipeline.

### Part A — MongoDB E11000

1. Create a test database and `event_inbox` collection.
2. Create a compound unique index `(tenantId, eventId)`.
3. Insert a document and re-insert with the same ID in `mongosh` to observe code `11000`.
4. Test a second unique index `(tenantId, deviceId, sequence)` with the same tuple and a new `eventId`.
5. Test missing/null fields and plan partial indexes/migrations if business needs them.
6. Compare `insert`, `save`, `upsert`, and conditional updates.

### Part B — Idempotent Inbox Service

1. Define `IncomingTelemetry` and `InboxEvent` entities using a stable ID.
2. Implement `MongoInboxIngestService.ingest(...)`.
3. Assert `INSERTED` on first call and `ALREADY_ACCEPTED` on redelivery with identical content.
4. Assert `CONFLICT` when ID matches but temperature/device differs.
5. Test E11000 from a secondary index where `findById` misses the expected ID.
6. Test two concurrent workers and assert only one inbox document exists.
7. Configure appropriate read preferences for post-timeout reconciliation.

### Part C — RetryAdvice

1. Create `RequestHandlerRetryAdvice` with `maxAttempts=3`.
2. Target `TransientDataAccessException` with `traversingCauses()`.
3. Attach it to either a `@ServiceActivator` or a Java DSL endpoint, not both.
4. Unit test that `DuplicateKeyException` is attempted **once**.
5. Unit test that transient errors undergo bounded retries.
6. Test recovery channels; distinguish an in-memory `ErrorMessage` from a durable DLQ.
7. Test HTTP/JMS/Kafka ACKs when the DB is down to prevent premature ACKs.

### Part D — Driver, Bulk, and Unknown Outcomes

1. On a test replica set, enable Retryable Writes.
2. Compare driver retries, Spring Retry, and broker redelivery.
3. Simulate a lost ACK after insert; retry using **the same business ID**.
4. Reconcile canonical payloads without generating a new UUID.
5. Run an unordered bulk insert containing one duplicate and inspect which documents persisted.
6. Avoid retrying the whole batch with new IDs; handle per-item outcomes.
7. Test the `NoWritesPerformed` label where supported by your version.

### Part E — Reliability and Operations

1. Write inbox + outbox inside a MongoDB transaction; test rollback when the outbox insert fails.
2. Simulate a crash after broker publish ACK before marking `SENT`.
3. Add an idempotent consumer keyed by event ID and assert a single business effect.
4. Implement atomic `findAndModify` claiming with owner/lease/version.
5. Add DLQ/quarantine handling and a reconciliation runbook.
6. Instrument metrics for same-payload duplicates vs. conflicts, attempts, exhausted retries, and unknown outcomes.
7. Test graceful shutdown with pending inbox/outbox events.

**Self-assessment questions:**

- What does E11000 indicate, and is it always a duplicate `_id`?
- Can E11000 happen on `update`/`upsert`/bulk/index builds?
- Why does E11000 not by itself prove two payloads are identical?
- How do `insert` and `save` differ when an ID already exists?
- Why does `exists() → insert()` fail to prevent races?
- What issues do null/missing values cause in unique indexes?
- When do you return `ALREADY_ACCEPTED` vs. `CONFLICT`?
- Why should `MessageHeaders.ID` never be used as a dedup key?
- How do driver retryable writes differ from Spring Retry?
- How many handler invocations does `maxAttempts(3)` allow?
- Why is `DuplicateKeyException` normally not retried?
- Why is cause traversal critical when errors are wrapped inside `MessagingException`?
- How can a lost ACK turn a retry into E11000?
- Can `ErrorMessageSendingRecoverer` cause upstream to ACK prematurely?
- How do stateful retry and broker redelivery differ from stateless retry?
- What specifically does the `NoWritesPerformed` label mean?
- Can an unordered bulk insert partially succeed?
- Are E11000 errors from upserts inside MongoDB 8.1 transactions retried automatically?
- When a transaction commit response is lost, can you assume it definitely rolled back?
- Why does an outbox still require an idempotent consumer?
- How do you test both valid duplicates and conflicting duplicates concurrently?

## 27. References

- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/): unique constraints, null/missing values, partial indexes, and sharded indexes.
- [MongoDB Manual — insertOne](https://www.mongodb.com/docs/manual/reference/method/db.collection.insertOne/): error `11000` examples.
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/): driver retries, topology, and `NoWritesPerformed`.
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/): transaction retries/error labels and duplicate upserts.
- [MongoDB Manual — bulkWrite](https://www.mongodb.com/docs/manual/reference/method/db.collection.bulkWrite/): ordered/unordered execution and partial successes.
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): ACKs, durability, and `wtimeout`.
- [Spring Data MongoDB — CRUD Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): insert/save/update/upsert/bulk.
- [Spring Framework API — DuplicateKeyException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/DuplicateKeyException.html): DAO exception hierarchy.
- [Spring Integration — MongoDB Support](https://docs.spring.io/spring-integration/reference/mongodb.html): inbound/outbound/gateway.
- [Spring Integration — Provided Advice Classes](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html): `RequestHandlerRetryAdvice`, stateless/stateful retry, and recoverers.
- [Spring Integration API — RequestHandlerRetryAdvice 6.4](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.html): `setRetryTemplate` and recovery callbacks.
- [Spring Retry API — RetryTemplateBuilder 2.x](https://docs.spring.io/spring-retry/docs/2.0.x/apidocs/spring.retry/org/springframework/retry/support/RetryTemplateBuilder.html): `maxAttempts`, `retryOn`, `traversingCauses`, `exponentialBackoff`.
- [Spring Data MongoDB — Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): `MongoTransactionManager`, `ReactiveMongoTransactionManager`.
- [Project Reactor — Reference](https://projectreactor.io/docs/core/release/reference/): `retryWhen`/`onErrorResume`.
- [Project Reactor — StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html): testing `Publisher` and `onError`.

## Conclusion

**E11000 is a unique-index constraint violation, not a signal to retry blindly.** In **SPRING_INTEGRATION_ADAPTERS**, proper handling begins with **stable business event IDs**, unique constraints, and classifying **INSERTED / ALREADY_ACCEPTED / CONFLICT** after verifying actual record contents. `insert` fits immutable event inboxes; `save` can overwrite state and is not a deduplication tool on its own.

Retries must be designed **by error class and by layer**: MongoDB driver Retryable Writes, Spring Integration retry advice, broker redeliveries, and HTTP retries each have distinct responsibilities. Never retry duplicate keys infinitely; never assume a timeout means a write did not occur; never ACK solely because a message entered an in-memory channel. For workflows spanning MongoDB/Kafka/JMS/HTTP/SFTP, combine **durable inbox/outbox, atomic claim/lease, idempotent consumers, bounded retries, reconciliation, metrics, and recovery** to preserve correctness across crashes and redeliveries.

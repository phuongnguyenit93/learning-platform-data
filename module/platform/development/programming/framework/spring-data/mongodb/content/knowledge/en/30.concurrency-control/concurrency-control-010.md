# Version limitations during direct updates or bulk writes

## 1. Problem: one document, two concurrent update streams

In an order management system using **Spring Data MongoDB**, a single order document can be updated by multiple flows: staff confirming orders, stock-reservation tasks, payment webhooks, and batch synchronization jobs.

Suppose two workers read the same state:

```javascript
{
  _id: "ord-101",
  tenant_id: "tenant-A",
  status: "PENDING",
  reserved_units: NumberLong("2"),
  version: NumberLong("7")
}
```

After reading:

```text
T1: Worker A reads order ord-101, version=7.
T2: Worker B reads order ord-101, version=7.
T3: A confirms the order and writes status=CONFIRMED.
T4: B writes an old status/new value based on the stale read.
```

If both streams update solely by `_id`, one operation can **overwrite the other's result** (*lost update*) or make business decisions on outdated state.

Spring Data MongoDB supports **optimistic locking** with `@Version` when saving entities through eligible APIs. However, when using **`MongoTemplate.updateFirst(...)`**, `findAndModify(...)`, **`BulkOperations.updateOne(...)`**, or the raw MongoDB Driver, you must understand precisely which version checks happen automatically and which must be done **explicitly**.

**Topic belonging to the Concurrency Control chapter** of the **SPRING_DATA_MONGODB** module: connecting, mapping documents, and operating on MongoDB via `MongoTemplate` or repositories; applying queries, aggregations, indexes, transactions, reactive access, testing, and performance diagnostics.

Lesson objectives:

- Use `expectedVersion` to prevent updates based on stale records.
- Understand the difference between **incrementing the version number** and **checking version before writing**.
- Build **compare-and-set (CAS)** with `Query` + `Update` in a single atomic command.
- Include CAS inside each operation of a **bulk write** without confusing total matched counts with per-line results.
- Distinguish **version conflicts**, **missing documents**, **business-condition rejections**, and **uncertain network outcomes**.
- Know when to use repository `save`, `findAndModify`, transactions, idempotency keys, and retries.

**Core principle:** for direct updates, the filter must contain **ID + expected version** (and appropriate tenant/business rules), while the update must **increment version inside the exact same atomic operation**. Incrementing version without comparing the old version **does not prevent lost updates**.

## 2. Compare-and-set formula in MongoDB

Suppose the document currently has `version = 7`. A worker issues "change status if the record is still at version 7":

```javascript
db.orders.updateOne(
  {
    _id: "ord-101",
    tenant_id: "tenant-A",
    version: NumberLong("7"),
    status: "PENDING"
  },
  {
    $set: {
      status: "CONFIRMED",
      last_operation_id: "confirm:ord-101:v7"
    },
    $inc: {
      version: NumberLong("1")
    },
    $currentDate: {
      updated_at: true
    }
  }
);
```

If the query matches a document, MongoDB executes the update on it **atomically**; status becomes `CONFIRMED` and version increments to 8 in one operation.

If another worker already bumped version to 8 beforehand, the `version:7` filter no longer matches and the command **does not** overwrite the newer state.

### 2.1. Invariant to preserve

```text
Precondition:
    document.id       == orderId
    document.tenant   == trustedTenantId
    document.version  == expectedVersion
    document.status   == PENDING

Atomic effect on match:
    status    := CONFIRMED
    version   := version + 1
    updatedAt := serverTime
    marker    := operationId
```

This is business-level CAS: mutate only when data still matches expectations.

### 2.2. Never use non-atomic three-step read-check-write

A dangerous implementation:

```java
OrderDocument current =
    template.findById(id, OrderDocument.class);

// Checking version in Java.
if (current.version().equals(expectedVersion)) {
    // Another worker can interleave before this command runs.
    template.updateFirst(
        Query.query(Criteria.where("id").is(id)),
        new Update().set("status", "CONFIRMED"),
        OrderDocument.class
    );
}
```

The interval between reading and updating is a **race window**. Instead of checking version solely in Java, move the version condition into **the write command's filter**.

### 2.3. Single-document atomicity does not turn an entire bulk batch into a transaction

Each `updateOne` on a single document protects the atomicity of that single command. A bulk batch of 100 `updateOne` operations across 100 documents **does not guarantee** all succeed or roll back together. Atomicity scopes and retry workflows must be designed separately.

## 3. Entity model with `@Version` and BSON mapping

We use an immutable Java record entity:

```java
import java.time.Instant;

import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders")
public record OrderDocument(
    @MongoId(FieldType.STRING)
    String id,

    @Field("tenant_id")
    String tenantId,

    String status,

    @Field("reserved_units")
    long reservedUnits,

    @Version
    Long version,

    @Field("updated_at")
    Instant updatedAt,

    @Field("last_operation_id")
    String lastOperationId,

    @Field("last_operation_hash")
    String lastOperationHash
) {}
```

Key highlights:

| Java property | BSON field | Meaning |
| --- | --- | --- |
| `id` | `_id` | Stable document key |
| `tenantId` | `tenant_id` | Partition and authorization filter |
| `reservedUnits` | `reserved_units` | Reserved quantity; updated conditionally |
| `version` | `version` | Version used for optimistic locking |
| `updatedAt` | `updated_at` | Write timestamp; never replaces version |
| `lastOperationId` | `last_operation_id` | Marker for retry reconciliation |
| `lastOperationHash` | `last_operation_hash` | Payload fingerprint for the same operationId |

Choose wrapper `@Version Long` so it stays `null` before initial insert. In Spring Data, starting versions for numeric wrappers typically begin at **0**; primitive versions typically use a different starting value, such as **1**. Version initialization rules must be verified by testing against your exact version.

Never assign `Instant.now()` as a "replacement version": timestamps can collide within clock resolution, suffer clock skew, or get computed prior to the write. Integer versions with CAS conditions clearly order changes on a document.

### 3.1. Mapping by Java property names

When calling `MongoTemplate` with `OrderDocument.class`:

```java
Criteria.where("tenantId").is("tenant-A")
    .and("version").is(7L);
```

Spring Data translates Java `tenantId` to BSON `tenant_id`. With the raw driver or `mongosh`, write the actual BSON field name.

Never write `Criteria.where("tenantId")` in raw MongoDB shell expecting Java `@Field` metadata to apply there.

## 4. How does `@Version` protect `save(...)`?

When using repositories or `MongoTemplate.save(...)` on an entity with `@Version`, Spring Data MongoDB applies optimistic locking on eligible save paths: the update filters by **ID and current version**, bumps version on write, and detects when no document matches.

```java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {}
```

Example with two flows saving loaded entities:

```java
OrderDocument a = repository.findById("ord-101")
    .orElseThrow();
OrderDocument b = repository.findById("ord-101")
    .orElseThrow();

// Illustrates creating new record copies with the same ID and version.
OrderDocument changedA = new OrderDocument(
    a.id(), a.tenantId(), "CONFIRMED",
    a.reservedUnits(), a.version(),
    a.updatedAt(), a.lastOperationId(), a.lastOperationHash()
);

OrderDocument changedB = new OrderDocument(
    b.id(), b.tenantId(), "CANCELLED",
    b.reservedUnits(), b.version(),
    b.updatedAt(), b.lastOperationId(), b.lastOperationHash()
);

OrderDocument savedA = repository.save(changedA);

// If both initially read version 7,
// save(changedB) must encounter an optimistic locking conflict.
repository.save(changedB);
```

When version has changed, eligible `save` paths throw **`OptimisticLockingFailureException`** instead of silently overwriting with the stale entity.

**Mandatory condition:** use an **acknowledged write concern** so the client receives the write result needed for optimistic locking checks. With `w:0`/unacknowledged writes, the app has no reliable proof of `matched=0`; avoid that setting for data needing CAS.

### 4.1. `@Version` is not a database lock

Optimistic locking:

- Does not hold an external mutex on the document before editing.
- Does not stop another worker from **reading** the same version.
- Does not automatically enforce multi-document business rules.
- Does not turn `saveAll(...)` across multiple documents into a transaction.
- Does not protect raw driver/`BulkOperations` commands just because the entity carries the annotation.

It is truly effective when **every relevant write path** obeys the same version protocol.

### 4.2. When is `save(...)` a good fit?

`save` fits when the application loads and edits **the entire aggregate/entity** and wants Spring Data mapping, callbacks, and versioning per contract. When only changing one field or performing an atomic `$inc`, direct updates with CAS are cleaner and avoid shipping full entities over the wire.

Choose based on data characteristics rather than forcing everything into `save` or everything into raw updates.

## 5. Direct updates: version may increment without necessarily being matched

A very common point of confusion in Spring Data MongoDB: `updateFirst(...)`/`updateMulti(...)` using `Update` do not receive a full **entity snapshot** from which Spring Data could infer the version the caller read.

In modern Spring Data MongoDB lines, a `@Version` property gets **auto-incremented after an update if it is absent from the `Update` definition**. Yet that auto-increment mechanism **does not automatically add an `expectedVersion` comparison predicate to your query**.

Dangerous example:

```java
Query query = Query.query(
    Criteria.where("id").is("ord-101")
);

Update update = new Update()
    .set("status", "CONFIRMED");

template.updateFirst(
    query, update, OrderDocument.class
);
```

Even though the mapping infrastructure bumps `version` on execution, the filter relies solely on ID. Two workers reading the same stale data can still write conflicting decisions by ID because **there is no expected-version comparison**.

**Distinguish the two responsibilities:**

| Capability | What does it solve? |
| --- | --- |
| `$inc: {version:1}` | Marks that the document moved to a new revision |
| Filter `version == expectedVersion` | Blocks a stale request from overwriting a newer revision |
| Both inside **the same updateOne** | Forms verifiable CAS |
| `@Version` on `save(...)` | Spring Data performs entity optimistic locking on eligible API paths |

To keep direct-update code easy to verify and independent of whether Spring Data auto-adds an increment, this lesson **explicitly increments version with `Update.inc("version",1L)`** and always puts `expectedVersion` in the filter. Once you update version explicitly in `Update`, never increment it a second time.

## 6. `MongoTemplate.updateFirst(...)`: true CAS in one command

### 6.1. Command and result

```java
public record ConfirmOrderCommand(
    String orderId,
    String tenantId,
    long expectedVersion,
    String operationId,
    String payloadHash
) {}
```

Direct-update service example:

```java
import com.mongodb.client.result.UpdateResult;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

@Service
public class OrderCasService {

    private final MongoTemplate template;

    public OrderCasService(MongoTemplate template) {
        this.template = template;
    }

    public boolean confirm(ConfirmOrderCommand command) {
        if (command.orderId() == null
                || command.orderId().isBlank()
                || command.tenantId() == null
                || command.tenantId().isBlank()
                || command.expectedVersion() < 0
                || command.operationId() == null
                || command.operationId().isBlank()
                || command.payloadHash() == null
                || command.payloadHash().isBlank()) {
            throw new IllegalArgumentException(
                "Invalid CAS details"
            );
        }

        Query filter = Query.query(
            Criteria.where("id").is(command.orderId())
                .and("tenantId").is(command.tenantId())
                .and("version").is(command.expectedVersion())
                .and("status").is("PENDING")
        );

        Update update = new Update()
            .set("status", "CONFIRMED")
            .set("lastOperationId", command.operationId())
            .set("lastOperationHash", command.payloadHash())
            .inc("version", 1L)
            .currentDate("updatedAt");

        UpdateResult result = template.updateFirst(
            filter, update, OrderDocument.class
        );

        if (!result.wasAcknowledged()) {
            throw new IllegalStateException(
                "Missing acknowledgment for CAS update"
            );
        }

        return result.getMatchedCount() == 1L;
    }
}
```

Why does the query include `and("status").is("PENDING")`? Version protects against stale writes, while the state predicate enforces the **business rule** "only confirm pending orders". Another command carrying the right `expectedVersion` yet finding `CANCELLED` must not confirm.

Why must `Update.inc("version",1L)` sit inside the same update? If you `$set` status first and issue a separate version increment afterward, a gap opens between the two commands where another writer can read/write before version reflects the change.

### 6.2. Do not conclude exactly which error caused `matchedCount=0`

When `getMatchedCount()==0`, several possibilities exist:

- `orderId` does not exist or was deleted.
- `tenantId` is wrong or caller lacks access.
- `status` is no longer `PENDING`.
- `version` was changed by another writer.
- A prior attempt **already succeeded** and the client resent the old expectedVersion.

Thus `false` in the example means "no document matched all preconditions", **not definitive proof of a version conflict**. The service/application layer must classify after a reconciliation read while avoiding leaking order status across tenants.

### 6.3. Distinguishing `matchedCount` and `modifiedCount`

`getMatchedCount()` indicates whether a document matched the filter. `getModifiedCount()` reflects how many documents the server reports changed. In the example, a match triggers `$inc(version,1)`, changing the document so modified is usually 1; nevertheless, CAS contracts should check **matchedCount** and real state when needed.

If an update only `$set`s the same existing value without bumping version, matched can be 1 while modified is 0. Never assume `modifiedCount==0` automatically proves a version conflict.

## 7. `findAndModify(...)`: CAS and receiving the post-update document

When callers need **newVersion** immediately after writing, use `findAndModify` with `returnNew(true)`:

```java
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public OrderDocument confirmAndReturn(
    MongoTemplate template,
    ConfirmOrderCommand command
) {
    Query filter = Query.query(
        Criteria.where("id").is(command.orderId())
            .and("tenantId").is(command.tenantId())
            .and("version").is(command.expectedVersion())
            .and("status").is("PENDING")
    );

    Update update = new Update()
        .set("status", "CONFIRMED")
        .set("lastOperationId", command.operationId())
        .set("lastOperationHash", command.payloadHash())
        .inc("version", 1L)
        .currentDate("updatedAt");

    return template.findAndModify(
        filter,
        update,
        FindAndModifyOptions.options().returnNew(true),
        OrderDocument.class
    );
}
```

On match, the method returns the updated entity (e.g., version 8). On no-match, it returns `null`. Handle `null` as **did not satisfy all conditions**, rather than equating it automatically with a version conflict.

This helps when needing:

- The new version for an ETag / optimistic concurrency token.
- The updated document returned without a second `findById` round trip.
- Attaching an operation marker and observing the post-write state.

However, `findAndModify` can still suffer an **ambiguous outcome** if connection drops after the server wrote. Not receiving the entity **does not prove** the server left the document unchanged. Design idempotency/reconciliation per business needs.

## 8. Why must business conditions stay in CAS?

Version is a change-detection mechanism, not the sole source of business truth.

Example reserving 3 more items if sufficient available stock remains:

```javascript
db.inventory.updateOne(
  {
    _id: "sku-101",
    version: NumberLong("7"),
    available: { $gte: 3 }
  },
  {
    $inc: {
      available: NumberLong("-3"),
      reserved: NumberLong("3"),
      version: NumberLong("1")
    }
  }
);
```

Here the update achieves three goals:

1. Rejects requests based on an outdated version.
2. Never reserves beyond available quantity.
3. Adjusts quantities **in a single atomic update**.

Even if you checked `available>=3` **in Java** before updating by version, keep the quantity predicate in the filter: business invariants must be guarded when the server executes the write.

### 8.1. `$inc` is atomic yet does not guard against duplicate retries

`$inc` on one document is atomic, yet if a client times out after MongoDB incremented `reserved` and a job resends the request with **the new version** without a fixed `operationId`, the same effect can apply twice.

Version resolves **contention across revisions**; operationId/ledgers resolve **identifying one business effect across retries**. Both complement rather than replace each other.

## 9. `@Version` and `BulkOperations`: what is not automatic?

Spring Data MongoDB provides:

```java
template.bulkOps(
    BulkOperations.BulkMode.UNORDERED,
    OrderDocument.class
);
```

`BulkOperations` batches multiple write commands into a single bulk execution. Bulk paths **must not be expected to provide automatic optimistic locking like `repository.save(entity)`**: Spring Data has no individual entity snapshot/version per `Update` to infer what the caller read, nor does a bulk return full per-operation outcomes for every unmatched update.

Therefore, **never** write an ID-only bulk expecting `@Version` on the entity to protect all updates.

**Dangerous** example:

```java
BulkOperations bulk = template.bulkOps(
    BulkOperations.BulkMode.UNORDERED,
    OrderDocument.class
);

for (ConfirmOrderCommand command : commands) {
    bulk.updateOne(
        Query.query(
            Criteria.where("id").is(command.orderId())
        ),
        new Update().set("status", "CONFIRMED")
    );
}

bulk.execute();
```

This snippet omits tenant, expectedVersion, and status precondition; each command can overwrite based on stale state. Having `@Version` on the entity **is not enough** to turn an ID-only query into CAS.

### 9.1. The right way: CAS inside each `updateOne`

```java
Query filter = Query.query(
    Criteria.where("id").is(command.orderId())
        .and("tenantId").is(command.tenantId())
        .and("version").is(command.expectedVersion())
        .and("status").is("PENDING")
);

Update update = new Update()
    .set("status", "CONFIRMED")
    .set("lastOperationId", command.operationId())
    .set("lastOperationHash", command.payloadHash())
    .inc("version", 1L)
    .currentDate("updatedAt");

bulk.updateOne(filter, update);
```

Each operation is an **atomic conditional update** with its own preconditions and version increment. This works inside bulk because it relies on MongoDB `updateOne` semantics, not Spring Data auto-adding optimistic locks.

## 10. Bulk service with manifest and explicit validation

Suppose a batch job confirms multiple orders. Use `List<ConfirmOrderCommand>` from a manifest with stable IDs, `expectedVersion`s, and `operationId`s:

```java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import com.mongodb.bulk.BulkWriteResult;
import org.springframework.data.mongodb.core.BulkOperations;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public final class OrderBulkCasWriter {

    private final MongoTemplate template;

    public OrderBulkCasWriter(MongoTemplate template) {
        this.template = template;
    }

    public BulkWriteResult confirmMany(
        List<ConfirmOrderCommand> commands
    ) {
        if (commands == null || commands.isEmpty()) {
            throw new IllegalArgumentException(
                "Command list is empty"
            );
        }

        Set<String> touchedOrders = new HashSet<>();
        Set<String> operationIds = new HashSet<>();

        BulkOperations bulk = template.bulkOps(
            BulkOperations.BulkMode.UNORDERED,
            OrderDocument.class
        );

        for (ConfirmOrderCommand c : commands) {
            if (c.orderId() == null || c.orderId().isBlank()
                    || c.tenantId() == null
                    || c.tenantId().isBlank()
                    || c.expectedVersion() < 0
                    || c.operationId() == null
                    || c.operationId().isBlank()
                    || c.payloadHash() == null
                    || c.payloadHash().isBlank()) {
                throw new IllegalArgumentException(
                    "Invalid command"
                );
            }

            // Do not submit two updates for the same order
            // inside one unordered bulk.
            String orderKey = c.tenantId() + ":" + c.orderId();
            if (!touchedOrders.add(orderKey)
                    || !operationIds.add(c.operationId())) {
                throw new IllegalArgumentException(
                    "Duplicate order or operationId in bulk"
                );
            }

            Query filter = Query.query(
                Criteria.where("id").is(c.orderId())
                    .and("tenantId").is(c.tenantId())
                    .and("version").is(c.expectedVersion())
                    .and("status").is("PENDING")
            );

            Update update = new Update()
                .set("status", "CONFIRMED")
                .set("lastOperationId", c.operationId())
                .set("lastOperationHash", c.payloadHash())
                .inc("version", 1L)
                .currentDate("updatedAt");

            bulk.updateOne(filter, update);
        }

        return bulk.execute();
    }
}
```

Why reject two commands for the same order inside an **unordered bulk**? Because execution order is not guaranteed. Even with CAS, if two commands share `expectedVersion`, **at most one** can match, yet business logic cannot rely on input list position to decide which command wins. Deduplicate, merge, serialize per aggregate ID, or resolve by explicit policy before constructing the bulk.

**Remaining limitation:** the code above only dispatches CAS and returns `BulkWriteResult`. It **has not yet** built per-operation reconciliation, durable manifest storage, or dead-letter queueing. Those belong to the orchestration layer.

## 11. `ORDERED` and `UNORDERED`: do not change CAS nature

| Criterion | `ORDERED` | `UNORDERED` |
| --- | --- | --- |
| Logical command order | Follows input order | Order not guaranteed |
| On **write error** | Typically stops at first error | May continue remaining operations |
| On CAS **matchedCount=0** | Not necessarily a write error; can continue | Same |
| Already-succeeded updates | Not auto-rolled back outside a transaction | Not auto-rolled back outside a transaction |
| Connection drop mid-batch | May not know which commands wrote | May not know which commands wrote |
| Best suited for | Order-dependent steps or fail-fast batches | Independent operations after deduplication |

**A normal version mismatch does not make MongoDB throw a duplicate key or optimistic locking exception on `updateOne`.** It produces an **unmatched document**, meaning that operation's matched count is 0. Inside a bulk, that is normally not recorded as a `writeError` by operation index.

Do not expect an `ORDERED` bulk to halt immediately on a version conflict when filtering by `version`: an update matching 0 documents is a valid MongoDB command, not a write error forcing the bulk to stop.

### 11.1. A bulk batch may be split into multiple physical commands

Drivers and servers limit operation counts and BSON sizes per batch, so a large bulk can be split into smaller batches. That makes assuming "all updates executed at once like a transaction" even more wrong.

Manifest/checkpoint design and idempotency must still hold even if the job is interrupted between physical bulk chunks.

## 12. `BulkWriteResult`: totals are not per-order outcomes

After an acknowledged bulk:

```java
BulkWriteResult result = writer.confirmMany(commands);

if (!result.wasAcknowledged()) {
    throw new IllegalStateException(
        "Missing acknowledgment for bulk CAS"
    );
}

int matched = result.getMatchedCount();
int modified = result.getModifiedCount();
int inserted = result.getInsertedCount();

System.out.printf(
    "matched=%d modified=%d inserted=%d%n",
    matched, modified, inserted
);
```

Suppose you send three updates for three different orders:

```text
Index 0: ord-A expectedVersion=7
Index 1: ord-B expectedVersion=4
Index 2: ord-C expectedVersion=9

BulkWriteResult:
  matchedCount = 2
  modifiedCount = 2
```

You cannot tell from those two totals whether **ord-B** conflicted or **ord-C** conflicted. `BulkWriteResult` contains **aggregate counters**, not an ID-by-ID list of succeeded vs. unmatched `updateOne` commands.

`getUpserts()` carries indexes/IDs for upserts that inserted new documents, yet is **not** a complete status map for all conditional updates.

### 12.1. Server write errors differ from unmatched CAS

A `MongoBulkWriteException` (or Spring-translated exception) can expose `writeErrors` containing the **index** of commands hitting write errors such as schema violations, duplicate keys, or bad data.

However, `matchedCount=0` on a version-filtered `updateOne` **does not normally produce a writeError**. Never catch errors and assume every command not listed in `catch` succeeded its CAS check.

### 12.2. Never infer outcomes as "the first matchedCount items" in an ordered bulk

Even in `ORDERED` mode, `matchedCount` is a **sum**. If operation index 0 missed its version while index 1 matched, total `matched=1` does not mean index 0 succeeded. Only APIs returning per-ID details or post-bulk reconciliation reveal which succeeded.

## 13. Reconciling per-operation outcomes after a bulk

When the business must know **whether each individual order was confirmed**, an orchestrator can persist a manifest:

```json
{
  "batchId": "confirm-orders-2026-11-20",
  "operations": [
    {
      "operationId": "confirm:ord-A:v7",
      "orderId": "ord-A",
      "expectedVersion": 7,
      "desiredStatus": "CONFIRMED",
      "payloadHash": "hash-A"
    },
    {
      "operationId": "confirm:ord-B:v4",
      "orderId": "ord-B",
      "expectedVersion": 4,
      "desiredStatus": "CONFIRMED",
      "payloadHash": "hash-B"
    }
  ]
}
```

The hash values here are purely illustrative labels. Real systems must hash **canonical payloads** (business-meaningful fields with consistent serialization rules).

A reconciliation algorithm:

1. **Durably persist the manifest** before dispatching the bulk, with `operationId`s stable across retries.
2. Send conditional `updateOne` commands with `expectedVersion` and markers.
3. On acknowledged results, verify `matchedCount` matches the expected operation count; if not, mark the batch for reconciliation.
4. On network/timeout errors, mark **UNKNOWN**; never assume nothing wrote.
5. Re-read documents by `orderId` within tenant scope and compare version, status, and marker/hash.
6. Classify each into `APPLIED`, `CONFLICT`, `MISSING_OR_DENIED`, `BUSINESS_REJECTED`, or `UNKNOWN` per evidence.
7. Retry only eligible items after verification, recomputing `expectedVersion` and business rules.

### 13.1. Decision table after readback

| Observed data | Cautious interpretation |
| --- | --- |
| Matching `lastOperationId` and hash, desired status | Evidence this operation applied, **assuming marker and effect wrote atomically** |
| Version incremented, marker belongs to another operation | Another writer modified it; resolve conflict/merge |
| Version still equals expected, status still PENDING | Possibly not yet applied; still account for read consistency |
| Document missing under tenant-scoped query | Could be missing, deleted, or unauthorized; never leak casually |
| Matching marker ID with different hash | **CONFLICT**: same key with different payload |
| Missing marker and version bumped multiple times | Insufficient evidence; requires durable ledger/audit |
| Network error before response | **UNKNOWN**; do not assume rollback |

A single plain readback is not always enough to tell whether a request previously applied if multiple writers subsequently modified the document. The `lastOperationId` marker can be overwritten by a later operation. For long-lived proof, use a durable ledger/idempotency store with transactions or bounded embedded history per retention rules.

### 13.2. Bulk lacks a per-item matched map: design trade-off

If operation counts are small and **immediate per-item results are mandatory**, issue separate `findAndModify` calls (each returning the document or null) with bounded concurrency/backpressure. When throughput is critical, use bulk + **ID-based readback**, persist manifests, and accept the reconciliation complexity.

No single option is universally optimal; balance round trips, correctness, and error-reporting UX.

## 14. Idempotency: a version guard alone does not prove retries are safe

Suppose:

```text
Worker sends CAS expectedVersion=7, operationId=op-1.
Server executes: status=CONFIRMED, version=8, marker=op-1.
Response is lost.
Worker resends CAS expectedVersion=7, operationId=op-1.
Server returns matchedCount=0.
```

That is **correct CAS behavior**: the second attempt does not apply again. Yet the client cannot tell whether:

- The first call succeeded and the retry was blocked.
- Another writer consumed version 7 first.
- Status transitioned through another flow.

**Never turn `matchedCount=0` into "nothing was written" and resend with version=8.** If a worker recomputes against the new version and re-applies the same business effect without idempotency, it can trigger a duplicate effect.

### 14.1. Marker in the same document

```javascript
db.orders.updateOne(
  {
    _id: "ord-101",
    version: NumberLong("7"),
    last_operation_id: { $ne: "op-1" }
  },
  {
    $set: {
      status: "CONFIRMED",
      last_operation_id: "op-1",
      last_operation_hash: "hash-1"
    },
    $inc: { version: NumberLong("1") }
  }
);
```

Because the marker filter and marker/version update run in **one atomic updateOne**, the same operation cannot apply twice **while the marker remains intact and commands follow the design**.

However, storing only **lastOperationId** cannot guard against infinite replays if another command later overwrites that marker. For long-term at-most-once guarantees, use a durable ledger, unique operationIds, and atomic/transactional marker + effect pairing.

### 14.2. Fingerprints must be compared

If `op-1` originally requested `status=CONFIRMED` and a later call with `op-1` requests `status=CANCELLED`, that is a **payload conflict**, not a valid retry.

Marker or ledger records must store `payloadHash`/canonical payload. Never treat "operationId already present" as success without verifying matching business payload.

## 15. Why avoid upsert on queries containing version?

A common design mistake:

```javascript
db.orders.updateOne(
  {
    _id: "ord-101",
    version: NumberLong("7")
  },
  {
    $set: { status: "CONFIRMED" },
    $inc: { version: NumberLong("1") }
  },
  { upsert: true }
);
```

If document `ord-101` exists at version 8, the filter fails to match. Because `upsert:true` is set, the server may try **inserting a new document** from the filter/update instead of simply returning 0 matched. If the insert carries the same `_id`, you hit a **duplicate key** error; if ID constraints are loose, unwanted duplicate documents can be created.

The right approach when updating an entity that must already exist:

```javascript
db.orders.updateOne(
  { _id: "ord-101", version: NumberLong("7") },
  {
    $set: { status: "CONFIRMED" },
    $inc: { version: NumberLong("1") }
  },
  { upsert: false }
);
```

When **create-if-absent** is needed, design a dedicated insert flow with stable IDs/unique indexes, version initialization, and explicit duplicate/conflict handling. Never turn a version mismatch into an insert via an unexamined `upsert`.

### 15.1. Initial insert and missing version

A legacy document lacking `version` does not automatically have version 0 at the database level. Filtering `version:0` will not match it. Filtering `version:null` has semantics matching both null and missing fields, easily causing inconsistent update behavior.

Before enabling version guards on an existing collection, audit BSON types and backfill data/versions via a controlled migration.

## 16. `replaceOne`, `updateMulti`, and `saveAll`: do not replace per-document CAS

### 16.1. `replaceOne`

Replacement overwrites **the document contents** (aside from immutable constraints like `_id`), risking silent field loss if the replacement object omits fields. To use replacement in bulk, still filter by `_id + expectedVersion`, include the **new version** in the replacement, and preserve all required fields.

Do not assume passing an entity with `@Version` into any `bulk.replaceOne` overload gives automatic optimistic locking like `save`. Check the exact API contract and test the real BSON/query.

### 16.2. `updateMulti`

```java
template.updateMulti(
    Query.query(Criteria.where("status").is("PENDING")),
    new Update().set("status", "EXPIRED"),
    OrderDocument.class
);
```

This updates **multiple documents**, fitting broad batch policies **when per-document CAS is not needed**. However, if each order has a different `expectedVersion`, one shared status filter cannot verify each individual expected version.

A single `updateMulti` cannot return full per-order status; use batched `updateOne` commands with individual preconditions when needed.

### 16.3. `saveAll`

Repository `saveAll(...)` is convenient for multiple entities, yet **does not** mean "all save or none save". Depending on ID/version and execution path, multi-entity saves can partially fail outside a transaction.

When multi-document atomicity is required, use transactions on a supported deployment; never infer atomicity from the word "All" in a method name.

## 17. Multiple commands on the same document: ordering and version

Example with two requests targeting the same order:

```text
A: version=7, PENDING → CONFIRMED
B: version=7, PENDING → CANCELLED
```

If both use CAS on version and status, **at most one** applies first, assuming nothing resets the document back to version 7. This is **first successful compare-and-set wins**, not "first item in the input list wins".

In `UNORDERED` mode, MongoDB can execute updates out of input order; therefore **never rely on list order** for business precedence.

If business rules dictate `CANCELLED` must always take precedence over `CONFIRMED`, implement an explicit **state policy**—such as a state machine, per-ID serialized queue, precedence using trusted event timestamps plus version guards—rather than merely switching to ordered bulk.

### 17.1. Version is not the upstream source event timestamp

Events from external systems can arrive **out of order**—for instance, event version 10 arrives before event version 9. If the MongoDB entity version increments in arrival order, it does not understand upstream **sourceVersion**.

You may need **two separate fields**:

- `version`: optimistic lock revision of the MongoDB document.
- `sourceVersion` or `eventSequence`: upstream event order/version number.

Filters then enforce both source-ordering policy and optimistic revision instead of overloading one variable for two jobs.

## 18. Retrying version conflicts: reload, re-evaluate, then write

A valid optimistic-locking retry typically follows:

1. Observe that preconditions no longer matched.
2. Reload the record from a source with appropriate read consistency.
3. Determine whether **business rules still allow the change**.
4. Recompute the update from the fresh state rather than the stale snapshot.
5. Take the current version as the new `expectedVersion`.
6. Retry with backoff/bounded attempts; if conflicts persist, exit with an appropriate error code.

Example:

```text
Attempt 1:
  read version=7, status=PENDING
  CAS confirm expectedVersion=7 → matched=0

Readback:
  version=8, status=CANCELLED

Rule:
  CONFIRMED is forbidden after CANCELLED

Outcome:
  BUSINESS_REJECTED; DO NOT retry confirmation against version=8.
```

**Never automatically retry simply by incrementing `expectedVersion`.** Doing so turns optimistic locking from a safety guard into a loop that overwrites fresh data.

### 18.1. Bounded retry loops

```java
public enum CasDecision {
    APPLIED,
    ALREADY_APPLIED,
    CONFLICT,
    BUSINESS_REJECTED,
    UNKNOWN
}
```

Explicit domain outcome enums help services distinguish cases:

- `ALREADY_APPLIED`: marker/hash proves the same effect already wrote.
- `CONFLICT`: document changed and caller must resolve.
- `BUSINESS_REJECTED`: current state no longer permits the action.
- `UNKNOWN`: outcome unclear due to network error / missing evidence.
- `APPLIED`: acknowledgment received with proof the update succeeded.

In real retry loops, orchestration must persist `operationId`, track retry counts, backoff, deadlines, and eventual dead-letter/inspection. Never swallow network errors as `CONFLICT` since the command may have completed before the reply dropped.

## 19. Multi-document transactions: CAS must still honor invariants

A workflow may need to:

- Confirm an order.
- Deduct product stock.
- Write ledger/audit entries.

If these three steps span **multiple documents/collections**, CAS on the order alone does not make the workflow atomic.

MongoDB supports multi-document transactions on eligible deployments (configured replica set/sharded cluster). Spring Data MongoDB provides `MongoTransactionManager`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
class MongoTransactionConfig {

    @Bean
    MongoTransactionManager mongoTransactionManager(
        MongoDatabaseFactory factory
    ) {
        return new MongoTransactionManager(factory);
    }
}
```

Orchestrating service:

```java
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderWorkflowService {

    private final OrderCasService orders;

    public OrderWorkflowService(OrderCasService orders) {
        this.orders = orders;
    }

    @Transactional(
        transactionManager = "mongoTransactionManager"
    )
    public void confirmWithRelatedWrites(
        ConfirmOrderCommand command
    ) {
        boolean applied = orders.confirm(command);

        if (!applied) {
            throw new OptimisticLockingFailureException(
                "Order update precondition failed"
            );
        }

        // Add other MongoDB operations via repository/template
        // in the same transaction context, e.g., stock reserve and ledger write.
        // Do not call external HTTP/email assuming they can roll back.
    }
}
```

This code is a **transaction boundary skeleton**; related data steps are omitted. It demonstrates that when CAS fails to match, the service must **throw** so the transaction rolls back earlier writes rather than returning success after a business precondition missed.

### 19.1. Bulk and transactions

Bulk writes can execute inside a transaction when operations participate in the active session/transaction context and meet deployment limits. Still, transactions:

- Carry overhead and resource/time limits.
- Can hit write conflicts requiring **whole-transaction** retry per semantics.
- Do not turn `matchedCount=0` into an automatic exception: the application must check invariants itself.
- Can encounter **unknown commit results** if connectivity drops after commit; never assume rollback.
- Do not cover emails, HTTP calls, payment gateways, or external brokers.

Never hold a transaction open for hours to batch millions of documents. Partition by business invariants and use proper checkpoints/idempotency.

## 20. Reactive MongoDB: CAS remains a conditional update command

In WebFlux, use `ReactiveMongoTemplate` instead of wrapping blocking `MongoTemplate` calls inside `Mono.just(...)`.

```java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import reactor.core.publisher.Mono;

public Mono<Boolean> confirmReactive(
    ReactiveMongoTemplate template,
    ConfirmOrderCommand c
) {
    if (c.expectedVersion() < 0) {
        return Mono.error(
            new IllegalArgumentException("Negative version")
        );
    }

    Query filter = Query.query(
        Criteria.where("id").is(c.orderId())
            .and("tenantId").is(c.tenantId())
            .and("version").is(c.expectedVersion())
            .and("status").is("PENDING")
    );

    Update update = new Update()
        .set("status", "CONFIRMED")
        .set("lastOperationId", c.operationId())
        .set("lastOperationHash", c.payloadHash())
        .inc("version", 1L)
        .currentDate("updatedAt");

    return template.updateFirst(
        filter, update, OrderDocument.class
    ).map(result -> {
        if (!result.wasAcknowledged()) {
            throw new IllegalStateException(
                "Unacknowledged CAS write"
            );
        }
        return result.getMatchedCount() == 1L;
    });
}
```

Reactive CAS shares identical semantics:

- Version filter is mandatory.
- Version increment sits inside the atomic update.
- A `false` result does not by itself pinpoint a version conflict.
- Retrying/resubscribing the publisher can **resend the same command**.
- Network errors can produce ambiguous outcomes.
- `Flux`/`Mono` do not replace indexes, read concerns, or transactions.

Never call `block()` on the event loop. For reactive transactions, use `ReactiveMongoTransactionManager`/`TransactionalOperator` with proper reactive context rather than an imperative manager.

## 21. Write concern, read concern, and result guarantees

### 21.1. Acknowledged writes for CAS

A versioned update must distinguish:

- Server acknowledgment with `matchedCount=1`.
- Acknowledgment with `matchedCount=0`.
- Error/timeout leaving outcome unknown.

If write concern is unacknowledged (`w:0`), the app cannot reliably trust counts or optimistic locking exceptions. For critical data, use an acknowledged write concern; when stronger durability is required by deployment policy, consider `majority`.

`w:"majority"` raises durable-write acknowledgment requirements per MongoDB semantics, yet **does not** eliminate dropped responses after the server wrote. Version + idempotency/reconciliation remain essential.

### 21.2. Reconciliation reads need the right source

If you write to primary and read from a lagging secondary, the client can observe an old version and falsely conclude "not yet applied". For outcome verification, configure fitting read preferences/read concerns and consider sessions/causal consistency as needed.

Even reading from primary, without durable markers or ledgers, final state may not prove a specific operation applied if subsequent writers modified it afterward.

### 21.3. CAS does not prevent valid sequential overwrites

Two sequential requests with `expectedVersion` **7 then 8** can both succeed. Version blocks **stale requests**; it does not stop a brand new request at revision 8 from making an undesirable business change. State machines, ACLs, and filter/service validation are still needed.

## 22. Indexes and performance for conditional updates

With filter:

```javascript
{
  _id: "ord-101",
  tenant_id: "tenant-A",
  version: NumberLong("7"),
  status: "PENDING"
}
```

MongoDB has a default unique `_id` index. Because the query has equality on `_id`, the server locates the exact document very selectively and checks tenant/version/status.

**Do not add a `{_id:1,version:1}` index by default** just for version CAS. On normal collections, `_id` is already a unique locator; adding a version index can add write amplification with little gain.

If use cases query by `tenantId + status` **without knowing ID**, another index may be warranted:

```javascript
db.orders.createIndex(
  { tenant_id: 1, status: 1, updated_at: -1 },
  { name: "idx_orders_tenant_status_updated" }
);
```

This index accelerates listing orders by status/time; it does not turn an `updateMulti` into per-version CAS.

### 22.1. `explain("executionStats")` for the equivalent read path

```javascript
db.orders.find({
  _id: "ord-101",
  tenant_id: "tenant-A",
  version: NumberLong("7"),
  status: "PENDING"
}).explain("executionStats");
```

Observe:

| Signal | Question |
| --- | --- |
| `IXSCAN` / `IDHACK` / equivalent plan | Does it use the index to locate by ID? |
| `totalKeysExamined` | How many index keys were examined? |
| `totalDocsExamined` | Did it have to scan many documents? |
| `nReturned` | Expected document count? |
| p95/p99 update latency | Write conflicts/hotspots on the same order? |
| Retry rate | Is CAS seeing heavy contention? |
| Version conflict rate | Are business flows generating many stale writes? |
| Write concern timeouts | Many ambiguous outcomes needing reconciliation? |

`explain` on a **read query** evaluates lookup cost; it does not reflect total cost of updates, journaling, replication, callbacks, or lock contention. Use metrics, profiler, driver monitoring, and dedicated benchmarks for write paths.

### 22.2. Hot documents and contention

If one order is updated constantly by hundreds of workers, many CAS attempts fail as version advances rapidly. Adding indexes alone will not cure single-document contention.

Options:

- Batch or coalesce changes by aggregate ID.
- Partition/serialize work queues by key to cut contention.
- Switch to atomic counters/conditional updates if business rules allow.
- Eliminate unnecessary read-modify-write cycles.
- Tune retry/backoff and batch sizes.

## 23. Integration testing CAS against real MongoDB

Unit tests mocking `MongoTemplate.updateFirst` to return `matched=1` only test branching logic; they never prove MongoDB enforces filters/versions atomically. Run integration tests against real MongoDB, such as Testcontainers.

### 23.1. Testing version increment and rejecting stale writers

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;

import com.mongodb.client.result.UpdateResult;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

@DataMongoTest
class OrderVersionCasIntegrationTest {

    @Autowired
    MongoTemplate template;

    @Test
    void onlyOneWriterCanUseExpectedVersion() {
        String id = "cas-order-001";

        template.insert(new OrderDocument(
            id, "test-tenant", "PENDING",
            0L, null, Instant.EPOCH, null, null
        ));

        OrderDocument saved =
            template.findById(id, OrderDocument.class);

        assertThat(saved).isNotNull();
        long v0 = saved.version();

        UpdateResult first = casConfirm(
            id, "test-tenant", v0, "op-first"
        );

        UpdateResult stale = casConfirm(
            id, "test-tenant", v0, "op-second"
        );

        assertThat(first.getMatchedCount()).isEqualTo(1L);
        assertThat(stale.getMatchedCount()).isEqualTo(0L);

        OrderDocument after =
            template.findById(id, OrderDocument.class);

        assertThat(after.status()).isEqualTo("CONFIRMED");
        assertThat(after.version()).isEqualTo(v0 + 1L);
        assertThat(after.lastOperationId())
            .isEqualTo("op-first");
    }

    private UpdateResult casConfirm(
        String id,
        String tenant,
        long expected,
        String opId
    ) {
        Query filter = Query.query(
            Criteria.where("id").is(id)
                .and("tenantId").is(tenant)
                .and("version").is(expected)
                .and("status").is("PENDING")
        );

        Update update = new Update()
            .set("status", "CONFIRMED")
            .set("lastOperationId", opId)
            .inc("version", 1L);

        return template.updateFirst(
            filter, update, OrderDocument.class
        );
    }
}
```

This test runs two commands **sequentially** with the same `expectedVersion` to verify stale rejection; it is not yet a real multi-threaded stress test. To test concurrency, use barriers/latches so two workers read the initial version, submit CAS concurrently, and assert total successes equal 1.

With fixed IDs, tests must use isolated databases/collections or safe cleanup. Never wipe a shared collection just to seed fixtures.

### 23.2. Testing a bulk batch containing a stale expectedVersion

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;

import com.mongodb.bulk.BulkWriteResult;
import org.junit.jupiter.api.Test;
import org.springframework.data.mongodb.core.BulkOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

@Test
void bulkOnlyMatchesCurrentVersion() {
    template.insertAll(List.of(
        new OrderDocument(
            "bulk-cas-01", "test-tenant", "PENDING",
            0L, null, Instant.EPOCH, null, null
        ),
        new OrderDocument(
            "bulk-cas-02", "test-tenant", "PENDING",
            0L, null, Instant.EPOCH, null, null
        )
    ));

    OrderDocument one = template.findById(
        "bulk-cas-01", OrderDocument.class
    );

    OrderDocument two = template.findById(
        "bulk-cas-02", OrderDocument.class
    );

    BulkOperations bulk = template.bulkOps(
        BulkOperations.BulkMode.UNORDERED,
        OrderDocument.class
    );

    bulk.updateOne(
        Query.query(
            Criteria.where("id").is(one.id())
                .and("version").is(one.version())
                .and("tenantId").is("test-tenant")
        ),
        new Update().set("status", "CONFIRMED")
            .inc("version", 1L)
    );

    // Use a stale/mismatched expectedVersion for the second order.
    bulk.updateOne(
        Query.query(
            Criteria.where("id").is(two.id())
                .and("version").is(two.version() + 1L)
                .and("tenantId").is("test-tenant")
        ),
        new Update().set("status", "CONFIRMED")
            .inc("version", 1L)
    );

    BulkWriteResult result = bulk.execute();

    assertThat(result.wasAcknowledged()).isTrue();
    assertThat(result.getMatchedCount()).isEqualTo(1);
    assertThat(result.getModifiedCount()).isEqualTo(1);

    assertThat(
        template.findById(one.id(), OrderDocument.class)
            .version()
    ).isEqualTo(one.version() + 1L);

    assertThat(
        template.findById(two.id(), OrderDocument.class)
            .status()
    ).isEqualTo("PENDING");
}
```

This is an **illustrative test method placed inside the test class in section 23.1**, reusing its `template` field and imports; not a standalone Java file. It proves an unmatched operation does not make the whole bulk throw an optimistic locking exception.

### 23.3. Testing `@Version` with repository `save`

Also add a test that:

1. Inserts an entity with `@Version Long version`.
2. Reads two snapshots A and B.
3. Calls `repository.save(A)` successfully and checks version increments.
4. Calls `repository.save(B)` with the old version and asserts `OptimisticLockingFailureException`.
5. Verifies final persisted data matches A.

This contrasts **automatic optimistic locking in `save`** clearly against **explicit CAS** in direct updates/bulk.

### 23.4. Additional tests to cover

| Case | Expectation |
| --- | --- |
| `@Version` on `save` | New version increments; stale save blocked |
| Direct update by ID only | Demonstrates risk when omitting expectedVersion |
| Direct update ID+version | Only one writer using that version succeeds |
| Right version, wrong status | CAS misses due to business precondition |
| Wrong tenant | Cannot update out-of-scope order |
| Bulk one current, one stale | Aggregate matched 1; only one order's version bumps |
| Ordered bulk hits CAS no-match | Does not stop automatically without a write error |
| One bulk with two commands for same ID | Detected/deduplicated beforehand; never rely on unordered list position |
| Upsert containing version | Does not create unintended documents on version mismatch |
| Lost reply after update | Reconciles marker before retrying |
| Same operationId, different payload | Conflict detected |
| Legacy document missing version | Migration/no silent wrong-version application |
| Unacknowledged write concern | Never used as optimistic locking foundation |
| Multi-document transaction | Rolls back when CAS fails; handles unknown commits |
| Reactive CAS | Publisher emits proper result without blocking |
| Index / hot document | Verify latency, version conflict rate, `explain` |

## 24. Common mistakes

**Mistake 1 — "Just adding `@Version` makes every `MongoTemplate.updateFirst` optimistic locking."** No. You must include expectedVersion in the query or use an API path with an explicit CAS contract.

**Mistake 2 — "Incrementing version is enough."** No. If the filter only targets `_id`, two writers can still write values calculated from stale snapshots.

**Mistake 3 — "`matchedCount=0` is always a version conflict."** No. Missing ID, wrong tenant, mismatched status, or an already-applied retry can also yield 0.

**Mistake 4 — "Bulk throws an exception when one update mismatches version."** Not by default; an `updateOne` matching 0 documents is generally not a write error.

**Mistake 5 — "`BulkWriteResult.matchedCount=5` means the first 5 orders succeeded."** No. It is an aggregate sum with no per-command match map.

**Mistake 6 — "ORDERED bulk rolls back succeeded updates on error."** Not outside a transaction.

**Mistake 7 — "With two commands for the same order in an UNORDERED bulk, the later one wins."** Input ordering is not guaranteed.

**Mistake 8 — "Upsert filtering by version is a safe conflict-retry pattern."** No. When version differs, upsert can try inserting and trigger duplicate keys or bad documents.

**Mistake 9 — "After a timeout, resend the exact request with the new version."** Dangerous. Reconcile effects and idempotency first.

**Mistake 10 — "`modifiedCount=0` means version mismatched."** Not if the update was a no-op or had different semantics; CAS typically checks `matchedCount`.

**Mistake 11 — "Transactions automatically detect unmatched CAS and roll back."** Not if the app ignores the result and lets the transaction commit.

**Mistake 12 — "Version equals upstream event sequence."** Not necessarily. Keep document revision separate from source sequence.

**Mistake 13 — "Adding `{_id:1,version:1}` is always faster."** No; `_id` is already unique/indexed—measure actual performance.

**Mistake 14 — "Acknowledged write concern means UNKNOWN can never happen."** No. Connections can drop right after the server wrote.

**Mistake 15 — "Reactive `retryWhen` can replay `$inc`/CAS without checking outcomes."** No. Consider effects, markers, and policy.

## 25. Practice exercises by difficulty level

1. Create order `ord-101` with `status=PENDING` and `version=7` on test MongoDB.
2. Write a raw `updateOne` filtering only by `_id`; simulate two writers setting different statuses.
3. Add `version:7` to the filter and `$inc: {version:1}` to the update.
4. Run two updates with `expectedVersion=7`; verify only one matches.
5. Switch to `MongoTemplate.updateFirst` with a `@Version Long version` entity, keeping version in the query.
6. Remove version from the query and observe why auto-incrementing version (if supported by framework) fails to block stale writes.
7. Use `findAndModify(...returnNew(true))` to read the new version right after write.
8. Add precondition `status=PENDING` and try confirming an already-CANCELLED order.
9. Build a bulk batch of multiple `updateOne` calls with differing `expectedVersion`s.
10. Give one operation a stale `expectedVersion`, read `BulkWriteResult.getMatchedCount()`, and confirm there is no per-ID match map.
11. Try `ORDERED` and `UNORDERED`, distinguishing unmatched queries from write errors.
12. Put two commands for the same order into an unordered bulk; add a deduplication step.
13. Add operationId/marker/hash; simulate a lost response and read back before retrying.
14. Try `upsert:true` with a versioned filter on a test database; observe duplicate risk.
15. Write a `repository.save(...)` test for optimistic locking exceptions.
16. Test a transaction for order + ledger on a test replica set; roll back when one CAS misses.
17. Write `ReactiveMongoTemplate.updateFirst` with a version filter and test resubscription behavior.
18. Measure index/`explain` and p95/p99 update latency on a "hot order".
19. Design `APPLIED/ALREADY_APPLIED/CONFLICT/UNKNOWN` outcome classification for a retry job.
20. Run integration tests verifying no write path in the module accidentally bypasses the version policy.

## 26. Production deployment checklist

| Question | Condition to verify |
| --- | --- |
| Does entity have `@Version` of right type? | `Long` wrapper/primitive and BSON type match data |
| Which write paths use `save`? | Know when framework applies optimistic locking automatically |
| Which write paths use update/bulk/raw? | **Explicitly include expectedVersion in filters** |
| Does version increment atomically with business update? | `$inc(version,1)` or clear equivalent mechanism |
| Any double version increment? | Never bump twice via Update plus another mechanism |
| Does query enforce tenant/ACL? | Filter from trusted source; never leak cross-tenant data |
| Are business preconditions included? | Valid status/quantity/conditions inside the filter |
| Is CAS 0 matched handled? | Distinguish missing/conflict/retry/permission with evidence |
| Do bulk batches have independent ops? | Deduplicate same ID; never rely on unordered ordering |
| Bulk results are aggregate-only? | Manifest/readback for per-ID outcomes |
| Retries after timeout? | Handle UNKNOWN, markers/ledger, and payloadHash |
| Upsert with expectedVersion? | Avoid unintended inserts on version mismatch |
| Legacy documents missing version? | Migration planned; never treat missing as version=0 |
| Acknowledged write concern? | Never use `w:0` for optimistic locking |
| Consistent readback? | Appropriate read preference/concern |
| Multi-document transactions? | Proper manager/context; throw when CAS fails |
| Out-of-order incoming operations? | Separate doc revision from `sourceVersion` |
| Extra indexes needed? | `_id` usually suffices for single-order CAS; measure in practice |
| Concurrency tests present? | Stale save, stale update, bulk partial match, retry ambiguity |
| Monitoring in place? | Conflict rate, UNKNOWN rate, retry count, latency, hotspots |

## 27. References

APIs and behaviors depend on the exact **MongoDB Server**, **MongoDB Java Driver**, and **Spring Data MongoDB** versions your application runs. Specifically verify `save(...)` `@Version` handling, template-update version auto-increment, bulk writes, transactions, and driver exception translation on your exact dependencies.

- [Spring Data MongoDB — Optimistic Locking](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#mongo-template.optimistic-locking)
- [Spring Data MongoDB — Bulk Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html)
- [Spring Data MongoDB — BulkOperations Javadoc](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/BulkOperations.html)
- [Spring Data MongoDB — MongoTemplate CRUD](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html)
- [Spring Data MongoDB — Update API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/query/Update.html)
- [Spring Data MongoDB — FindAndModifyOptions API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/FindAndModifyOptions.html)
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/)
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)

**Conclusion:** `@Version` supports optimistic locking when saving entities through eligible APIs, yet **direct updates and bulk writes must never be assumed to automatically verify the caller's read version**. To constrain changes by version, combine **ID + tenant + expectedVersion + business conditions in the filter**, while **incrementing version inside the same atomic update**. In bulk writes, each `updateOne` needs its own CAS; `BulkWriteResult` provides aggregate counts only and does not automatically throw errors for unmatched commands. Finally, versioning stops stale snapshot overwrites yet **does not replace idempotency, post-timeout reconciliation, multi-document transactions, or upstream event ordering**. Verify with integration tests on real MongoDB and monitor conflict rates and latency before going to production.

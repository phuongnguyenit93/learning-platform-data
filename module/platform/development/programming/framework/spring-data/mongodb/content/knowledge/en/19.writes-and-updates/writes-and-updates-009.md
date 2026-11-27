# Preserving _id, Version, and Data Absent From the Java Model

> **Chapter:** Writes and Updates  
> **Module:** `SPRING_DATA_MONGODB`

In Spring Data MongoDB, a `save` call looks deceptively simple: load an entity, change its status, and save it back. Yet if the MongoDB document carries extra fields **not declared on the Java class**—such as legacy metadata, attributes written by another service, or fields added by a newer schema version—writing back the full entity can **drop data Java never loaded into the model**. At the same time, mishandling `_id` and `@Version` fields can overwrite the wrong document, insert unwanted records, or lose concurrent updates.

This lesson clearly separates **document replacement** from **partial updates**, explains the role of `_id` and optimistic locking via `@Version`, and demonstrates selective updates that preserve fields absent from the Java model. These are core concepts in the `SPRING_DATA_MONGODB` module: connecting and mapping documents, operating via `MongoTemplate` or repositories, designing queries, aggregations, indexes, transactions, reactive access, testing, and performance diagnostics.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish `insert`, `save`, `replace`, `updateFirst`, `findAndModify`, and `upsert` by their impact on BSON fields.
2. Explain why `_id` is **immutable** on an existing document and how `@Id`/`@MongoId` shape ID mapping.
3. Use `@Version` to catch stale-version updates, handle `OptimisticLockingFailureException`, and verify write concern.
4. Preserve legacy/unmapped fields via intentional `$set`/`$unset` while enforcing version predicates.
5. Avoid pitfalls when using partial updates, the raw driver, callbacks/auditing, transactions, and migrations of versionless legacy data.
6. Write integration tests proving invariants on `_id`, `version`, and fields absent from the Java model.

## 2. Real-World Problem: The BSON Document Is Wider Than the Java Entity

Suppose the database holds an order document created by an older application:

```javascript
{
  _id: "ORD-100",
  tenantId: "TENANT-A",
  status: "NEW",
  amountMinor: NumberLong(150000),
  version: NumberLong(3),
  legacy_note: "Reconciled with legacy system",
  externalPayload: {
    source: "warehouse-v1",
    trackingKey: "WH-7788"
  },
  updatedAt: ISODate("2026-11-18T08:00:00Z")
}
```

The current Java model knows only `id`, `tenantId`, `status`, `amountMinor`, `version`, and `updatedAt`. It **does not declare** `legacy_note` or `externalPayload`. When reading BSON into the entity, `MappingMongoConverter` typically ignores fields unmapped by the model.

That **does not** mean unknown fields were deleted during the read. MongoDB still stores the complete document. The danger arises when the application **writes back** the record via a path that replaces the entire document.

### 2.1. Three Easily Confused Operations

```text
MongoDB before update:
  _id, tenantId, status, version, legacy_note, externalPayload
                          |
           +--------------+-----------------+
           |              |                 |
      save(entity)     $set(status)       $unset(legacy_note)
           |              |                 |
           v              v                 v
   Writes new entity   Changes only       Removes only the
    representation       status           specified field
           |              |                 |
   Unmapped fields     Unknown fields     Other fields
    may vanish         are preserved      are preserved
```

In a persisted document, **`_id` is the identity**, **`version` is the application's concurrency guard** when using `@Version`, and **legacy fields are real data** requiring an explicit preservation or migration policy. These three concerns relate closely, yet no single annotation solves all three at once.

## 3. Comparison of Write Paths

| Operation | Primary Meaning | Fields Absent From Entity / Replacement BSON | Impact on ID / Version |
| --- | --- | --- | --- |
| `MongoTemplate.insert(entity)` | Inserts a new document | Writes only mapped fields | Generates/uses `_id`; initializes `@Version` appropriately |
| `MongoRepository.save(entity)` | Saves new entity or updates existing entity | **Risk of loss** when replacing document | Uses ID and version handling per mapping |
| `MongoTemplate.save(entity)` | Persists entity per mapping | **Risk of loss** as document is rebuilt from entity | Handles `@Id` and `@Version` per API |
| `MongoTemplate.replace(query, entity, options)` | Replaces matching document with new representation | **Risk of loss** due to full replacement | Must keep valid `_id`; check version contract separately |
| `MongoTemplate.updateFirst(query, update, Entity.class)` | Selective field update | **Preserves** fields untouched by `$set`/`$unset` | Keeps `_id`; framework may auto-increment version if omitted from `Update` |
| `MongoTemplate.updateMulti(...)` | Updates multiple documents | **Preserves** fields outside update scope | Does not enforce per-entity optimistic locking without explicit version predicate |
| `MongoTemplate.findAndModify(...)` | Finds and modifies one document conditionally | **Preserves** untouched fields | Can return pre/post image; design version check explicitly |
| Raw driver `updateOne(..., {$set:...})` | Direct BSON update | **Preserves** fields outside update scope | Bypasses Spring custom mapping and automatic `@Version` |
| Raw driver `replaceOne(...)` | Direct document replacement | **Drops** fields omitted from replacement | Immutable `_id`; no automatic optimistic locking |
| `upsert` | Update if matched, insert if missing | Depends on update vs. replacement form | Can insert a new document; verify keys, version, and races |

**Read the table in context:** Spring Data methods apply different mapping rules, entity callbacks, and version logic depending on version and overload. Never assume they behave identically simply because they all write to the same collection.

## 4. _id Is Immutable: Keeping Identity Intact on Write

MongoDB requires each document in a collection to have a unique `_id`; a document **cannot change its `_id` value** once created. When a new `_id` differs from the old `_id`, it is not an "in-place primary key edit."

### 4.1. Distinguishing _id, Java id, and Business Codes

File `OrderRecord.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public class OrderRecord {

    @Id
    private String id;
    private String tenantId;
    private String status;
    private long amountMinor;
    @Version
    private Long version;
    private Instant updatedAt;

    protected OrderRecord() {}

    public OrderRecord(
            String id, String tenantId, String status,
            long amountMinor, Instant updatedAt) {
        this.id = id;
        this.tenantId = tenantId;
        this.status = status;
        this.amountMinor = amountMinor;
        this.updatedAt = updatedAt;
    }

    public String getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public long getAmountMinor() {
        return amountMinor;
    }

    public Long getVersion() {
        return version;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public void setUpdatedAt(Instant updatedAt) {
        this.updatedAt = updatedAt;
    }
}
```

`@Id` maps property `id` to `_id`. Here `ORD-100` is not shaped like a valid ObjectId, so it stores cleanly as a BSON String. For 24-hex-character String IDs, Spring Data may convert them to BSON ObjectId by default; when strict BSON type control is required, consider `@MongoId` or appropriate `FieldType` metadata and test historical data.

**Do not let clients edit `id` via an update DTO.** Operations like "change order code" should modify a separate business field `orderCode` if required, never assign a new value to `id` on an existing document.

### 4.2. Immutable _id Example in mongosh

```javascript
// ANTI-PATTERN: MongoDB forbids changing _id of an existing document.
db.orders.updateOne(
  { _id: "ORD-100" },
  { $set: { _id: "ORD-NEW" } }
)
```

This operation fails because it attempts to alter `_id`. Likewise, calling `replaceOne` with a replacement whose `_id` differs from the matched document is invalid.

```javascript
// Keep _id, change only status:
db.orders.updateOne(
  { _id: "ORD-100" },
  { $set: { status: "PAID" } }
)
```

**Note on `save` with a modified id:** the application may target the wrong document, insert a new record, or hit optimistic locking/duplicate key errors depending on the call path and entity state; never treat mutating Java `id` as a command to rename `_id` in MongoDB.

### 4.3. How insert, save, and upsert Differ When a Document Is Missing

`insert` is an **add-only** operation that fails if `_id` already exists. `save` creates or updates an entity per Spring Data mapping semantics; do not treat it as "update just one field."

`upsert` means **update if matched, insert if missing**. If the user asked to *modify only an existing order*, prefer `updateFirst` **without upsert** and check `matchedCount`. Enabling upsert carelessly can create incomplete records or expand data scope unexpectedly.

## 5. @Version: Detecting Updates Based on Stale Reads

`@Version` is Spring Data MongoDB's **optimistic locking** mechanism. Each entity carries a version stored in the document. When saved through an optimistic-locking-aware API, the framework adds a predicate requiring the **current version to match**; if another writer modified the record first, the stale update is rejected.

### 5.1. Example: Two Concurrent Writers Editing One Order

```text
Initially: document has _id=ORD-100, version=3

Worker A                       Worker B
   |                              |
   +-- reads version=3            +-- reads version=3
   |                              |
   +-- save(status=PAID)          |
   |   predicate version=3        |
   |   succeeds -> version=4      |
   |                              +-- save(status=CANCELLED)
   |                                  predicate version=3
   |                                  mismatch -> error
   v
B does not silently overwrite A's update.
```

Without version checks, a "read–modify–write back" cycle risks *lost updates*: the later writer silently clobbers the earlier writer's changes.

### 5.2. Initial Version Values

For a wrapper `@Version Long version`, Spring Data typically initializes version to **0** on insert; for primitive numeric types, the starting value per version rules may be **1**. This lesson uses `Long` to cleanly distinguish `null` before insert and inspect legacy data lacking a version field.

Version is not a timestamp and does not tell you when an event happened; it is a **sequence number for write concurrency control**. Do not increment it manually in business code when using Spring Data write paths that already manage version, unless you have a specific tested reason.

### 5.3. Repository.save With Version

File `OrderRepository.java`:

```java
package com.example.shop.orders;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderRecord, String> {
}
```

Service example:

```java
OrderRecord order = repository.findById("ORD-100")
    .orElseThrow();

order.setStatus("PAID");
repository.save(order);
```

If another writer altered the document after `findById`, `save` throws `OptimisticLockingFailureException` instead of silently overwriting. Return an appropriate conflict error to the client, or reload and merge according to business rules. **Never retry the exact stale entity by forcing its version up.**

Spring Data optimistic locking requires **write acknowledgment**. With `WriteConcern.UNACKNOWLEDGED`, the application may fail to detect a missed version match. Ensure the environment uses an acknowledged write concern and test contention against a real database.

### 5.4. @Version Is Not Natively Enforced by MongoDB Server

MongoDB itself sees only a plain `version` field and query filters. When Spring Data executes an optimistic-locking save, the framework translates the contract into a version predicate on the write and checks the write result. A raw driver command such as:

```javascript
db.orders.updateOne(
  { _id: "ORD-100" },
  { $set: { status: "PAID" } }
)
```

**Does not automatically check or increment `version`** just because the Java class has `@Version`. If multiple services or workers update the same collection, align all write paths—including batch jobs and migrations—on one versioning protocol.

## 6. Why Can save Drop Fields Absent From the Java Model?

Recall `OrderRecord` from Section 4 **does not declare** `legacy_note` or `externalPayload`. When executed:

```java
OrderRecord order = repository.findById("ORD-100")
    .orElseThrow();

order.setStatus("PAID");
repository.save(order);
```

The read maps only recognized properties. When saving back, Spring Data serializes BSON from the current model and executes a full save/replacement. The resulting record can look like:

```javascript
{
  _id: "ORD-100",
  tenantId: "TENANT-A",
  status: "PAID",
  amountMinor: NumberLong(150000),
  version: NumberLong(4),
  updatedAt: ISODate("2026-11-18T08:00:00Z"),
  _class: "com.example.shop.orders.OrderRecord"
  // legacy_note and externalPayload are gone.
}
```

Key points:

1. **`_id` remains intact** when save updates the original document properly.
2. **`version` increments cleanly** and optimistic locking still works.
3. **Unmapped fields can still disappear** because the new representation excludes them.

Hence **`@Version` does not protect unmapped fields**. It solves a separate problem: concurrent updates based on stale reads.

### 6.1. Losing a Field Differs From Writing Null

An entity property with `status = null` may be written as null or omitted depending on mapping settings. By contrast, Java has no awareness of `legacy_note` at all, so there is no value to include in the BSON replacement.

Do not expect `MappingMongoConverter` to preserve "unknown BSON leftovers" when saving an entity. Only a dedicated read/write extension mechanism or partial updates will intentionally preserve fields outside the model.

### 6.2. @Transient Does Not Preserve BSON Fields Either

`@Transient` instructs Spring Data **not to map** a Java property to the document. It is **not** an annotation for keeping an existing BSON field untouched.

```java
import org.springframework.data.annotation.Transient;

@Transient
private String temporaryDisplayLabel;
```

This merely marks a field as non-persistent. If old BSON contains a field of the same name that the model ignores, a replacement-style `save` can still wipe out that stored field.

## 7. Selective Updates: Preserving Fields Outside the Change Scope

If the requirement is "mark order PAID," the safe operation for unmapped data is usually **`$set` only the modified fields**, rather than rewriting the whole entity.

### 7.1. MongoDB $set

```javascript
db.orders.updateOne(
  {
    _id: "ORD-100",
    tenantId: "TENANT-A",
    version: NumberLong(3)
  },
  {
    $set: {
      status: "PAID",
      updatedAt: ISODate("2026-11-20T02:00:00Z")
    },
    $inc: { version: NumberLong(1) }
  }
)
```

This operation:

- Matches only when **ID, tenant, and version** all match.
- Updates `status`/`updatedAt`.
- Increments `version` in **the same atomic single-document update**.
- Leaves `legacy_note` and `externalPayload` untouched.

**This is a `mongosh` example, not Spring Data code.** With a Spring Data entity declaring `@Version`, certain update APIs **automatically increment** version if omitted from `Update`; do not copy `$inc version` and also trigger an automatic increment in Java without checking your API's exact behavior.

### 7.2. MongoTemplate.updateFirst With CAS

CAS (*compare-and-set*) checks the expected value directly inside the update predicate. File `OrderUpdateService.java`:

```java
package com.example.shop.orders;

import com.mongodb.client.result.UpdateResult;
import java.time.Clock;
import java.time.Instant;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

@Service
public class OrderUpdateService {
    private final MongoTemplate template;
    private final Clock clock;

    public OrderUpdateService(MongoTemplate template, Clock clock) {
        this.template = template;
        this.clock = clock;
    }

    public void markPaid(
            String permittedTenantId,
            String orderId,
            long expectedVersion) {

        if (permittedTenantId == null
                || permittedTenantId.isBlank()) {
            throw new IllegalArgumentException("Invalid tenant");
        }
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("Invalid ID");
        }
        if (expectedVersion < 0) {
            throw new IllegalArgumentException("Invalid version");
        }

        Query query = Query.query(
            Criteria.where("id").is(orderId)
                .and("tenantId").is(permittedTenantId)
                .and("version").is(expectedVersion));

        Update update = new Update()
            .set("status", "PAID")
            .set("updatedAt", Instant.now(clock));

        UpdateResult result =
            template.updateFirst(query, update, OrderRecord.class);

        if (result.getMatchedCount() != 1) {
            throw new OptimisticLockingFailureException(
                "Order missing, out of scope, or version changed");
        }
    }
}
```

In this example:

- `Criteria.where("id")` is the Java property mapped to BSON `_id`.
- `tenantId` is a mandatory data boundary; the application must authorize it prior to calling.
- `version` is checked directly in the update predicate, avoiding races between `findById` and `save`.
- `Update` **does not** modify `_id`, **does not** rewrite the object, and does not enable `upsert`.
- Under Spring Data MongoDB's mapping/version handling, `@Version` on supported updates typically **auto-increments** if no version change is declared in `Update`. Never increment twice manually.
- `getMatchedCount() == 0` signals not-found/modified/unauthorized; do not leak cross-tenant resource existence to clients.

A `Clock` bean can be registered as:

```java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TimeConfig {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

**Crucial distinction:** `updateFirst` does not automatically compare against an old version on every call just because `@Version` exists. The predicate `version == expectedVersion` is placed in `Query` **explicitly** here. Auto-incrementing version on update and **checking the caller's expected version** are two distinct behaviors.

### 7.3. matchedCount Differs From modifiedCount

`UpdateResult.getMatchedCount()` tells whether any document satisfied the filter, whereas `getModifiedCount()` tells whether MongoDB actually changed document bytes.

Do not use `modifiedCount == 0` as proof a document doesn't exist: a no-op update (setting the exact current value) can match without modifying. When version bumps apply, no-op behavior can vary by API; still rely primarily on `matchedCount` alongside write acknowledgment to confirm CAS matched.

## 8. Intentional Field Removal With $unset, Not Accidental Replacement

If business rules decide `legacy_note` should be retired, express that deletion explicitly:

```javascript
db.orders.updateOne(
  { _id: "ORD-100" },
  { $unset: { legacy_note: "" } }
)
```

In Spring Data:

```java
Update update = new Update()
    .unset("legacy_note");

template.updateFirst(
    Query.query(Criteria.where("id").is("ORD-100")),
    update,
    OrderRecord.class);
```

This snippet assumes placement inside a service/class holding `MongoTemplate template`; in production, also include tenant, version predicates, and result checks as in Section 7. When updating a `@Version` entity, the framework may update version along supported API paths.

If the goal is to **keep** `legacy_note`, never pass it to `$unset`. Every legacy field cleanup should have a migration plan, estimated document count, reconciliation, and recovery plan.

### 8.1. Why Field-Level Updates Fit Multi-Service Shared Schemas Better

When multiple services share a collection, one service owns `status` and `updatedAt` while another adds `externalPayload`. If both perform full replacements using their own models, they can **delete each other's data**.

Selective updates help reduce that hazard:

```text
Service Orders:       $set(status, updatedAt)
Service Integration:  $set(externalPayload.trackingKey)
Service Compliance:   $set(legacy_note)
```

Still, two updates touching **the same field** can overwrite each other. To prevent *lost updates* on the same field or cross-field invariants, pair with CAS/version predicates or appropriate transactions.

### 8.2. Updating Nested Fields With Dot Notation

To update only the tracking key:

```javascript
db.orders.updateOne(
  { _id: "ORD-100" },
  { $set: { "externalPayload.trackingKey": "WH-9000" } }
)
```

This preserves `externalPayload.source`. Conversely:

```javascript
db.orders.updateOne(
  { _id: "ORD-100" },
  { $set: { externalPayload: { trackingKey: "WH-9000" } } }
)
```

**replaces the whole `externalPayload` object**, losing `source`. "`$set` preserves other fields" holds only **outside the target path**; `$set` on a parent subdocument drops unmentioned sibling subfields.

## 9. findAndModify: Conditional Update and Read Result

When you need the post-update document immediately, Spring Data MongoDB offers `findAndModify`. Unlike separate "find then update," find-and-modify runs on MongoDB within a single command.

Example:

```java
import java.time.Instant;
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

Query query = Query.query(
    Criteria.where("id").is("ORD-100")
        .and("tenantId").is("TENANT-A")
        .and("version").is(3L));

Update update = new Update()
    .set("status", "PAID")
    .set("updatedAt", Instant.parse("2026-11-20T02:00:00Z"));

OrderRecord updated = template.findAndModify(
    query,
    update,
    FindAndModifyOptions.options().returnNew(true),
    OrderRecord.class);

if (updated == null) {
    throw new IllegalStateException(
        "ID/tenant/version did not match");
}
```

`returnNew(true)` requests the **post-update document**; default behavior on `findAndModify` overloads returns the **pre-update** image. `null` indicates no document matched the conditions. Upsert is disabled here; if enabling upsert, design new-document creation and identity keys carefully.

Fields absent from the model **remain in BSON after the update**, though the returned Java object maps only properties declared on `OrderRecord`. Thus reading the Java object and not seeing `legacy_note` **does not mean it was deleted**; inspect raw BSON directly.

## 10. Special Case: Keeping Unknown Fields via Map or Converter

Some applications want to capture arbitrary extension metadata and persist it back. You can **design the schema** with an explicitly named map:

```java
import java.util.Map;
import org.springframework.data.mongodb.core.mapping.Field;

@Field("extensions")
private Map<String, Object> extensions;
```

This maps the **BSON field `extensions`**, for example:

```javascript
{
  _id: "ORD-100",
  extensions: {
    source: "warehouse-v1",
    trackingKey: "WH-7788"
  }
}
```

**It does not automatically capture arbitrary unknown root-level fields** like `legacy_note` or `externalPayload`. Never assume adding `Map<String,Object>` to an entity causes Spring Data to retain all unmapped root BSON fields automatically.

When you truly need to round-trip arbitrary BSON documents with unknown schemas, consider:

- A **`org.bson.Document` model** via driver/`MongoTemplate` with controlled merge logic.
- **Custom conversions** mapping legacy formats while explicitly preserving contracted fields.
- A **dedicated extension field** (such as `extensions`) that newer versions know how to read and write.
- **Partial updates** so services never touch fields they do not own.

Never write a client-supplied `Document` back to the database without field allowlists and authorization checks: clients could otherwise tamper with `_id`, `version`, `tenantId`, or internal fields.

## 11. Legacy Documents Lacking a Version Field

A common scenario is a v1 document stored as:

```javascript
{
  _id: "ORD-LEGACY",
  tenantId: "TENANT-A",
  status: "NEW"
  // No version field present.
}
```

When the updated Java entity adds `@Version Long version`, `version` loads as `null` from old documents. In Spring Data, a `null` version often signals a **new** entity, causing `save` to follow the insert path and throw a **duplicate key** error instead of updating. Never run bulk `save` over legacy data without testing this case.

### 11.1. Version Backfill Strategy

One approach is backfilling the version field in a controlled migration:

```javascript
// ILLUSTRATIVE ONLY: run after verifying data integrity,
// service deployment ordering, and write-path impact.
db.orders.updateMany(
  { version: { $exists: false } },
  { $set: { version: NumberLong(0) } }
)
```

This initializes version on documents missing it; it **does not resolve races** with concurrent writers. You may need to coordinate writers, batch the migration, or deploy compatible readers/writers before enforcing strict optimistic locking.

Never blindly force `version: 0` across all documents: documents that already hold higher versions or active transactions must stay untouched.

### 11.2. V1 Data Holding a Different Version Type

If v1 stored `version: "3"` (BSON String) while v2 expects `Long`, server queries for `version: NumberLong(3)` will **not match** String-typed documents, even if a custom converter reads them into Java. Convert the stored BSON type or maintain an explicit compatibility strategy; changing only the Java field type is not enough.

Likewise, if v1 named the field `revision` while v2 uses `version`, add `@Field("revision")` or migrate per contract. Never assume existing documents automatically contain `version` simply because you annotated `@Version` in Java.

## 12. Write Paths That Can Bypass Spring Version Controls

| Write Path | Preserves Unrelated Fields? | Automatically Checks Caller's Expected Version? |
| --- | --- | --- |
| `repository.save(versionedEntity)` | Not guaranteed; may write full replacement | **Yes**, via supported optimistic locking |
| `template.save(versionedEntity)` | Not guaranteed; may write full replacement | **Yes**, along supported save/version paths |
| `template.updateFirst(query, update, Entity.class)` | Yes, with selective updates | **Only if query includes version predicate**; framework may auto-increment version |
| `template.findAndModify(query, update, ...)` | Yes | **Only if query includes version predicate**; framework may auto-increment version |
| `template.updateMulti(...)` | Yes | Requires explicit predicate design; does not replace per-entity optimistic locking |
| `template.getCollection(...).updateOne(...)` | Yes | **Not automatic**; caller must put version in filter and `$inc` if needed |
| `db.orders.updateOne(...)` in `mongosh` | Yes | **Not automatic**; depends on author's filter/update |
| `db.orders.replaceOne(...)` | No | **Not automatic**; requires version predicate and complete replacement |

The key takeaway of this table is that **auto-incrementing version** differs from **checking expected version before writing**. A steadily increasing version never prevents lost updates if callers omit expected version from the filter.

### 12.1. Raw MongoDB Driver: Implementing Full CAS Manually

When using the driver directly:

```java
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

UpdateResult result = template.getCollection("orders")
    .updateOne(
        new Document("_id", "ORD-100")
            .append("tenantId", "TENANT-A")
            .append("version", 3L),
        new Document("$set",
            new Document("status", "PAID"))
            .append("$inc",
                new Document("version", 1L))
    );

if (result.getMatchedCount() != 1) {
    throw new IllegalStateException("Version mismatch");
}
```

This snippet assumes placement inside a class holding `MongoTemplate template`. It uses **raw BSON field names** directly and bypasses Spring's entity mapping, custom converters, auditing callbacks, and automatic optimistic locking. Match exact BSON types for `_id` and `version`, update audit/timestamps manually if required, and check write acknowledgment.

### 12.2. Auditing Callbacks Are No Silver Bullet for Partial Updates

When an entity declares `@LastModifiedDate`, standard `save(entity)` flows fire entity callbacks/auditing to refresh timestamps. An `Update.set(...)` command does not necessarily pass through the same full-entity callback pipeline.

Therefore, in partial updates, set required audit fields such as `updatedAt` and `updatedBy` explicitly. If your app has complex audit policies, test the exact overload in use and centralize write logic in services so every write path honors one contract.

## 13. Integration Testing: Inspecting BSON Before and After Writes

To verify this lesson's concepts, unit tests mocking `OrderRepository` are **insufficient**. Mocks return canned objects without proving whether `save` wipes out unmapped fields, `updateFirst` bumps version, or CAS blocks stale writes.

Use a dedicated test MongoDB instance and seed v1 documents **directly via the raw driver**. That ensures fixtures carry fields unknown to the Java entity.

### 13.1. JUnit 5: Seeding Legacy Data

Example using Spring Boot Data MongoDB Test and AssertJ. File `OrderWriteCompatibilityTest.java`:

```java
package com.example.shop.orders;

import com.mongodb.client.result.UpdateResult;
import java.time.Instant;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
class OrderWriteCompatibilityTest {

    @Autowired
    MongoTemplate template;

    private static final String ID = "ORD-100";

    @BeforeEach
    void seed() {
        // Connect ONLY to an isolated test MongoDB instance.
        var collection = template.getCollection("orders");
        collection.deleteMany(new Document());

        collection.insertOne(
            new Document("_id", ID)
                .append("tenantId", "TENANT-A")
                .append("status", "NEW")
                .append("amountMinor", 150000L)
                .append("version", 3L)
                .append("updatedAt",
                    java.util.Date.from(Instant.parse(
                        "2026-11-18T08:00:00Z")))
                .append("legacy_note",
                    "Reconciled with legacy system")
                .append("externalPayload",
                    new Document("source", "warehouse-v1")
                        .append("trackingKey", "WH-7788"))
        );
    }

    private Document raw() {
        return template.getCollection("orders")
            .find(new Document("_id", ID))
            .first();
    }

    @Test
    void readingEntityDoesNotDeleteUnknownFields() {
        OrderRecord entity = template.findById(
            ID, OrderRecord.class);

        assertThat(entity).isNotNull();
        assertThat(entity.getId()).isEqualTo(ID);
        assertThat(entity.getVersion()).isEqualTo(3L);
        assertThat(entity.getStatus()).isEqualTo("NEW");

        Document stillStored = raw();
        assertThat(stillStored).isNotNull();
        assertThat(stillStored.getString("legacy_note"))
            .isEqualTo("Reconciled with legacy system");
        assertThat(stillStored.get(
            "externalPayload", Document.class).getString("source"))
            .isEqualTo("warehouse-v1");
    }

    @Test
    void fullSaveCanDiscardUnmappedFields() {
        OrderRecord entity = template.findById(
            ID, OrderRecord.class);
        assertThat(entity).isNotNull();
        entity.setStatus("PAID");

        template.save(entity);

        Document afterSave = raw();
        assertThat(afterSave).isNotNull();
        assertThat(afterSave.getString("_id")).isEqualTo(ID);
        assertThat(afterSave.getString("status"))
            .isEqualTo("PAID");
        assertThat(afterSave.get("version", Number.class)
            .longValue()).isEqualTo(4L);

        // This is the behavior TO CATCH, not a goal of dropping data.
        assertThat(afterSave.containsKey("legacy_note")).isFalse();
        assertThat(afterSave.containsKey("externalPayload"))
            .isFalse();
    }

    @Test
    void partialUpdatePreservesUnknownFieldsAndId() {
        Query condition = Query.query(
            Criteria.where("id").is(ID)
                .and("tenantId").is("TENANT-A")
                .and("version").is(3L));

        Update changes = new Update()
            .set("status", "PAID")
            .set("updatedAt", Instant.parse(
                "2026-11-20T02:00:00Z"));

        UpdateResult result = template.updateFirst(
            condition, changes, OrderRecord.class);
        assertThat(result.getMatchedCount()).isEqualTo(1);

        Document afterUpdate = raw();
        assertThat(afterUpdate).isNotNull();
        assertThat(afterUpdate.getString("_id"))
            .isEqualTo(ID);
        assertThat(afterUpdate.getString("status"))
            .isEqualTo("PAID");
        assertThat(afterUpdate.get("version", Number.class)
            .longValue()).isEqualTo(4L);

        assertThat(afterUpdate.getString("legacy_note"))
            .isEqualTo("Reconciled with legacy system");
        Document external = afterUpdate.get(
            "externalPayload", Document.class);
        assertThat(external.getString("source"))
            .isEqualTo("warehouse-v1");
        assertThat(external.getString("trackingKey"))
            .isEqualTo("WH-7788");
    }

    @Test
    void staleVersionCannotOverwriteWinner() {
        Query v3 = Query.query(
            Criteria.where("id").is(ID)
                .and("tenantId").is("TENANT-A")
                .and("version").is(3L));

        UpdateResult first = template.updateFirst(
            v3,
            new Update().set("status", "PAID"),
            OrderRecord.class);

        UpdateResult stale = template.updateFirst(
            Query.query(
                Criteria.where("id").is(ID)
                    .and("tenantId").is("TENANT-A")
                    .and("version").is(3L)),
            new Update().set("status", "CANCELLED"),
            OrderRecord.class);

        assertThat(first.getMatchedCount()).isEqualTo(1);
        assertThat(stale.getMatchedCount()).isZero();
        assertThat(raw().getString("status")).isEqualTo("PAID");
        assertThat(raw().get("version", Number.class)
            .longValue()).isEqualTo(4L);
    }
}
```

**Warning:** `collection.deleteMany(new Document())` wipes the **entire `orders` collection in the connected database**. Run this test strictly against an isolated MongoDB instance such as Testcontainers with test config that can never point to production. `@DataMongoTest` imports may differ across Spring Boot major versions; verify against your dependencies.

These examples assume `OrderRecord` mapping is active and `@Version Long version` from Section 4 works on the test MongoDB instance. Gradle/tests were not executed while authoring this document; these tests serve as reference code for projects to implement and verify.

### 13.2. Why Must Tests Seed Data via the Raw Driver?

If you seed fixtures via:

```java
template.insert(new OrderRecord(
    "ORD-100", "TENANT-A", "NEW", 150000L,
    Instant.parse("2026-11-18T08:00:00Z")));
```

Spring Data writes only fields known to the Java model. Such a fixture **lacks `legacy_note` and `externalPayload` from the start**, so even if `save` drops legacy data, the test would never detect it.

Use `template.getCollection("orders").insertOne(new Document(...))` to seed BSON **genuinely containing legacy fields**. Then read with `MongoTemplate`, write with your application's actual API, and inspect via `getCollection(...)` to verify unmapped fields survived.

### 13.3. Evaluating Both Version and Untouched Data

Recommended test matrix:

| Scenario | Invariant to Confirm |
| --- | --- |
| Read-only entity from legacy BSON | Stored document remains unchanged |
| Full `save` on legacy entity | Detects unmapped-field loss; disallow this write path if forbidden |
| `updateFirst` with `$set` | `_id`, `legacy_note`, `externalPayload` stay intact |
| Two updates with same expectedVersion | Only one matches; version increments once |
| Update with wrong ID | `matchedCount = 0`; no accidental upsert |
| Update for unauthorized tenant | `matchedCount = 0`; other tenant untouched |
| `$set` on a nested subfield | Preserves sibling fields inside the object |
| `$set` replacing whole sub-object | Test reveals sibling fields are dropped |
| Document missing `version` | Migration or compatibility strategy in place; no blind `save` |
| Document with ObjectId vs. String `_id` | Queries and mapping never mismatch types |
| Update via raw driver | Explicit CAS/version and timestamps if required |
| Update via reactive API | BSON and version invariants match imperative behavior |
| Update under network/write failure | Does not report success without confirmed outcome per policy |

## 14. Transactions, Atomicity, and Consistency Do Not Replace Versioning

MongoDB applies a single update command to **one document** atomically. When `updateOne` checks `_id` + `version` and uses `$inc`, checking and updating happen in one operation, preventing two writers holding the same version from both succeeding.

However:

- Multi-document transactions solve **cross-document invariants**; they do not fix an app saving a replacement missing legacy fields.
- If two writers read stale data and each runs `$set` without a CAS condition, the final state still depends on which fields changed and execution order.
- A transaction lacking proper version/business conditions can still misbehave on client retries or stale reads.
- Retrying writes must account for **idempotency**. Retrying `$inc: { amountMinor: 100 }` can add twice without an operation key or deduplication guard.

**Principle:** use selective updates to preserve unmapped data; use expected version/CAS to block stale writes; use transactions when multi-document atomicity is needed. They address **three distinct concerns**.

## 15. Using ReactiveMongoTemplate

In reactive access, building `Query` and `Update` works the same way, while methods return `Mono<UpdateResult>`:

```java
import com.mongodb.client.result.UpdateResult;
import reactor.core.publisher.Mono;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public Mono<Void> markPaidReactive(
        ReactiveMongoTemplate template,
        String tenantId,
        String id,
        long expectedVersion) {

    Query condition = Query.query(
        Criteria.where("id").is(id)
            .and("tenantId").is(tenantId)
            .and("version").is(expectedVersion));

    Update changes = new Update()
        .set("status", "PAID");

    return template.updateFirst(
            condition, changes, OrderRecord.class)
        .flatMap(result -> {
            if (result.getMatchedCount() != 1) {
                return Mono.error(
                    new IllegalStateException(
                        "ID/tenant/version mismatch"));
            }
            return Mono.<Void>empty();
        });
}
```

This is an illustrative method inside a Java service class; the caller must authenticate `tenantId`, validate inputs, and subscribe to the publisher to execute the update. Add required auditing timestamps to `Update` if needed. In reactive tests, use `StepVerifier` to assert both success and CAS conflict errors.

**Reactive does not alter BSON rules:** `$set` still preserves fields outside the modified path, raw driver calls still ignore `@Version`, and saving a full entity still risks dropping unmapped fields.

## 16. Operational Checklist Before Changing Write Paths

1. **Snapshot the actual schema:** inventory all stored fields, including unmapped fields, nested objects, fields owned by other services, and BSON types.
2. **Define field ownership:** may this service delete metadata from another service? Which fields must survive migrations?
3. **Lock down identity:** verify `_id` BSON types and keep `_id` immutable on updates; separate `_id` from mutable business codes.
4. **Pick the write path:** use `save` only when persisting full controlled entity state; use `updateFirst`/`findAndModify` for targeted modifications.
5. **Protect concurrency:** verify `@Version` and write concern; in partial updates, place expectedVersion in the query per policy.
6. **Control upsert:** disable upsert on update-only paths and inspect `matchedCount`.
7. **Audit and timestamps:** set `updatedAt`/`updatedBy` explicitly on partial updates if entity callbacks do not apply.
8. **Migrate legacy versions:** plan for documents missing `version` or holding mismatched types.
9. **Test real BSON:** seed unknown fields with the raw driver, run both save and patch, and assert `_id`, version, and unknown fields before/after.
10. **Monitor in production:** track optimistic-lock conflicts, no-match updates, duplicate keys, retries, and migration errors; log only necessary IDs/metadata, never sensitive payloads.

## 17. Common Errors

| Symptom | Root Cause | Fix |
| --- | --- | --- |
| `legacy_note` vanishes after `save` | Entity omits the field; save replaces document | Use targeted `$set`/`$unset` or model an explicit extension schema |
| Version increments yet external service data disappears | Optimistic locking checks stale writes, not unknown fields | Separate data-preservation strategy from versioning strategy |
| `updateFirst` silently ignores stale version | Query lacks expected version or caller ignores result | Add version predicate and inspect `matchedCount` |
| Version increments twice | Manual `inc("version")` paired with framework auto-increment | Pick one mechanism and verify post-update BSON |
| Cannot find 24-hex-char ID documents | String ID mapped to ObjectId while legacy BSON stores String | Audit `@Id`/`@MongoId` mapping and actual BSON types |
| Mutating Java `id` creates duplicate or errors | `_id` cannot be modified in place | Keep `_id` immutable; add a separate business code field |
| Legacy versionless document errors on write | Null version treated as new entity or violates contract | Backfill/migrate and test legacy documents explicitly |
| `$set` on whole sub-object loses siblings | Replaced parent object path | Use dotted path for the exact subfield |
| `@LastModifiedDate` stays stale on partial update | Update path bypasses save callbacks | Set auditing fields explicitly |
| Raw driver write bypasses version and converters | Bypasses Spring mapping infrastructure | Implement CAS, BSON mapping, auditing, and result checks manually |
| Update-only endpoint creates incomplete document | Upsert enabled unintentionally | Separate update from create; keep upsert off for updates |
| Mock tests pass, production loses data | Mocks lack BSON unknown fields | Seed raw BSON in integration tests and assert field preservation |

## 18. Practice Exercise

An inventory system stores a document:

```javascript
{
  _id: "SKU-001",
  tenantId: "T-A",
  quantity: NumberLong(25),
  version: NumberLong(9),
  updatedAt: ISODate("2026-11-19T08:00:00Z"),
  supplierData: {
    supplierId: "SUP-7",
    restockCode: "RST-99"
  },
  legacyTags: ["fragile", "priority"]
}
```

The new Java application maps only `id`, `tenantId`, `quantity`, `version`, and `updatedAt`. It must deduct 3 units for a stock-out slip:

1. Why does reading the entity, decrementing `quantity`, and calling `save` risk data loss?
2. Write an `updateOne` checking `_id`, tenant, version 9, and `quantity >= 3`, then using `$inc` to decrement quantity and increment version **once**.
3. Write the equivalent `MongoTemplate.updateFirst` with `Criteria` and `Update.inc("quantity", -3)`, accounting for Spring Data's `@Version` auto-increment behavior.
4. If two requests both read version 9, what happens to the second write?
5. Verify afterward that `supplierData.supplierId` and `legacyTags` remain unchanged.
6. If legacy documents lack `version` or store `quantity` as a BSON String, how should they be handled before enabling CAS?
7. If the stock-out request retries after a timeout, how do you prevent deducting quantity twice?

**Guidance:** full-entity `save` can drop unmapped fields. Use an atomic conditional update:

```javascript
db.stock.updateOne(
  {
    _id: "SKU-001",
    tenantId: "T-A",
    version: NumberLong(9),
    quantity: { $gte: NumberLong(3) }
  },
  {
    $inc: {
      quantity: NumberLong(-3),
      version: NumberLong(1)
    },
    $set: {
      updatedAt: ISODate("2026-11-20T02:00:00Z")
    }
  }
)
```

In Spring Data, add only `inc("quantity", -3)` and the expected version predicate; do not manually increment version if updating a `@Version` entity already managed by the framework. Check `matchedCount` to separate success from failed predicates. For retries on stock deductions, use an idempotency key on the slip or an explicit deduplication guard so the same business command never applies twice.

## 19. References

- Spring Data MongoDB — [Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): `save`, `updateFirst`, `findAndModify`, replace/upsert, and optimistic locking with `@Version`.
- Spring Data MongoDB — [Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): `@Id`, `@MongoId`, `@Field`, `@Transient`, and entity mapping metadata.
- Spring Data MongoDB — [Auditing](https://docs.spring.io/spring-data/mongodb/reference/mongodb/auditing.html): auditing callbacks and timestamps.
- MongoDB Manual — [Update Documents](https://www.mongodb.com/docs/manual/tutorial/update-documents/): `$set`, `$unset`, `$inc`, and update atomicity.
- MongoDB Manual — [replaceOne](https://www.mongodb.com/docs/manual/reference/method/db.collection.replaceOne/): replacement, upsert, and `_id` constraints.
- MongoDB Manual — [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/): atomic single-document operations and conditional updates.

## Key Takeaways

**`_id`** must remain immutable during document updates. **`@Version`** catches stale writes across supported Spring Data APIs, yet does not protect BSON fields unknown to the Java entity. **`save`/replace** can write a representation stripped of legacy fields, whereas **selective `$set`/`$unset`** preserves untouched data. When both correctness and schema compatibility matter, use **CAS with expected version**, update only targeted fields, verify write results, and test against real legacy BSON before deploying to production.
